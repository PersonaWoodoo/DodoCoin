import json
import random
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from database import DB_PATH, modify_balance
import aiosqlite
import time

router = Router()

# Хранилище для антифлуда: {user_id: timestamp}
last_clicks = {}
FLOOD_TIMEOUT = 0.5
# Настройки игры
GRID_SIZE = 25
MINES_COUNT = 6
MULTIPLIER_STEP = 1.15
ADMIN_IDS = [8478884644]

DEFAULT_EMOJIS = {
    "lose": "💣",
    "win": "🎉",
    "cashout": "✅",
}


# ─── ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ────────────────────────────────────────────────

async def get_emojis(db: aiosqlite.Connection) -> dict:
    emojis = dict(DEFAULT_EMOJIS)
    try:
        async with db.execute(
                "SELECT key, value FROM mine_settings WHERE key IN ('emoji_lose','emoji_win','emoji_cashout')"
        ) as cur:
            rows = await cur.fetchall()
            for key, val in rows:
                short = key.replace("emoji_", "")
                emojis[short] = val
    except Exception:
        pass
    return emojis


def fmt_num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def build_lose_text(mention: str, lost: int, could: int, emoji: str) -> str:
    return (
        f"<b>{mention}</b>\n"
        f"{emoji} <i>Увы, вы наткнулись на мину!</i>\n\n"
        f"<blockquote>Потеряно: <b>{fmt_num(lost)} dC</b>\n"
        f"Можно было забрать: <b>{fmt_num(could)} dC</b></blockquote>"
    )


def build_win_text(mention: str, lost: int, could: int, emoji: str) -> str:
    return (
        f"<b>{mention}</b>\n"
        f"{emoji} <i>Победа, вы победили!</i>\n\n"
        f"<blockquote>Потеряно: <b>{fmt_num(lost)} dC</b>\n"
        f"ВЫ выиграли: <b>{fmt_num(could)} dC</b></blockquote>"
    )


def build_cashout_text(mention: str, won: int, could: int, emoji: str) -> str:
    return (
        f"<b>{mention}</b>\n"
        f"{emoji} <i>Вы забрали выигрыш, вы победили!</i>\n\n"
        f"<blockquote>Потеряно: <b>0 dC</b>\n"
        f"Вы забрали: <b>{fmt_num(won)} dC</b></blockquote>"
    )


def build_cancel_text(mention: str) -> str:
    return (
        f"❌ <b>{mention}</b> вы отменили игру\n"
        f"<i>Ставка возвращена</i>"
    )


# ─── ПОЛЕ И КЛАВИАТУРА ──────────────────────────────────────────────────────

def generate_field():
    field = [0] * GRID_SIZE
    mines = random.sample(range(GRID_SIZE), MINES_COUNT)
    for m in mines:
        field[m] = 1
    return field


def get_keyboard(revealed, user_id, game_over=False, field=None):
    buttons = []
    row = []
    for i in range(GRID_SIZE):
        if i in revealed:
            text = "💣" if field and field[i] == 1 else " "
        else:
            text = "❓" if not game_over else ("💣" if field[i] == 1 else " ")
        row.append(InlineKeyboardButton(text=text, callback_data=f"m_{user_id}_{i}"))
        if len(row) == 5:
            buttons.append(row)
            row = []

    if not game_over:
        if not revealed:
            buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data=f"mquit_{user_id}")])
        else:
            buttons.append([InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data=f"mcash_{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── ФОНОВАЯ ЗАДАЧА ─────────────────────────────────────────────────────────

async def auto_refund_mines():
    while True:
        try:
            async with aiosqlite.connect(DB_PATH, timeout=30) as db:
                await db.execute("PRAGMA journal_mode=WAL;")
                async with db.execute(
                        "SELECT user_id, chat_id, bet FROM mine_games WHERE last_action < datetime('now', '-5 minutes')"
                ) as cur:
                    expired = await cur.fetchall()

                for uid, cid, bet in expired:
                    await modify_balance(uid, bet, db=db)
                    await db.execute("DELETE FROM mine_games WHERE user_id = ? AND chat_id = ?", (uid, cid))
                await db.commit()
        except Exception as e:
            logging.error(f"Ошибка в auto_refund: {e}")
        await asyncio.sleep(60)


async def ensure_mine_settings_table():
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("""CREATE TABLE IF NOT EXISTS mine_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
        for short, emoji in DEFAULT_EMOJIS.items():
            await db.execute("INSERT OR IGNORE INTO mine_settings (key, value) VALUES (?, ?)",
                             (f"emoji_{short}", emoji))
        await db.commit()


# ─── ХЕНДЛЕРЫ ───────────────────────────────────────────────────────────────

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.lower().startswith("мины "))
async def start_mine(message: Message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        return await message.reply("Используйте: мины (сумма)")

    bet = int(args[1])
    if bet <= 0:
        return await message.reply("❌ Ставка должна быть больше 0!")

    user_id = message.from_user.id
    fmt_user_id = f"@{user_id}"
    chat_id = message.chat.id

    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await db.execute("PRAGMA journal_mode=WAL;")

        async with db.execute("SELECT mines_status FROM group_settings WHERE chat_id = ?", (chat_id,)) as cur:
            settings = await cur.fetchone()
            if settings and settings[0] == 0:
                return await message.reply("🚫 <b>Мины</b> отключены администратором.", parse_mode="HTML")

        async with db.execute("SELECT bet, message_id FROM mine_games WHERE user_id = ? AND chat_id = ?",
                              (user_id, chat_id)) as cur:
            old = await cur.fetchone()
            if old:
                old_bet, old_msg_id = old
                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (old_bet, fmt_user_id))
                await db.execute("DELETE FROM mine_games WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
                await db.commit()
                try:
                    await message.bot.edit_message_text(chat_id=chat_id, message_id=old_msg_id,
                                                        text="<i>⚠️ Игра отменена. Ставка возвращена.</i>",
                                                        parse_mode="HTML")
                except:
                    pass

        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (fmt_user_id,)) as cur:
            user_data = await cur.fetchone()

        if not user_data or user_data[0] < bet:
            return await message.reply(f"❌ Недостаточно dC! Нужно: {fmt_num(bet)}", parse_mode="HTML")

        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (bet, fmt_user_id))
        field = generate_field()
        msg = await message.answer(
            f"<b>{message.from_user.mention_html()}</b>, игра началась!\n💰 Ставка: <b>{fmt_num(bet)} dC</b>\nОткрывайте ячейки 👇",
            reply_markup=get_keyboard([], user_id), parse_mode="HTML"
        )
        await db.execute(
            "INSERT INTO mine_games (user_id, chat_id, message_id, bet, mines_map, revealed_cells, last_action) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, chat_id, msg.message_id, bet, json.dumps(field), json.dumps([]))
        )
        await db.commit()


@router.callback_query(F.data.startswith("m_"))
async def click_cell(call: CallbackQuery):
    user_id = call.from_user.id
    current_time = time.time()

    # ПРОВЕРКА АНТИФЛУДА
    if user_id in last_clicks and current_time - last_clicks[user_id] < FLOOD_TIMEOUT:
        return await call.answer("Не так быстро! ⏳", show_alert=False)
    last_clicks[user_id] = current_time

    data = call.data.split("_")
    owner_id, cell_idx = int(data[1]), int(data[2])

    if user_id != owner_id:
        return await call.answer("Это не ваша игра!", show_alert=True)

    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        async with db.execute(
                "SELECT bet, mines_map, revealed_cells, message_id FROM mine_games WHERE user_id = ? AND chat_id = ?",
                (owner_id, call.message.chat.id)
        ) as cur:
            row = await cur.fetchone()

        if not row or call.message.message_id != row[3]:
            return await call.answer("Игра не найдена или устарела.", show_alert=True)

        bet, field_json, revealed_json, _ = row
        field, revealed = json.loads(field_json), json.loads(revealed_json)

        if cell_idx in revealed:
            return await call.answer()

        revealed.append(cell_idx)
        emojis = await get_emojis(db)

        if field[cell_idx] == 1:  # ПРОИГРЫШ
            await db.execute("DELETE FROM mine_games WHERE user_id = ? AND chat_id = ?",
                             (owner_id, call.message.chat.id))
            await db.commit()

            # Сначала отвечаем на Callback, чтобы избежать таймаута
            try:
                await call.answer("БОМБА! 💥")
            except Exception:
                pass

            mult_could = round(MULTIPLIER_STEP ** len(revealed), 2)

            # Защита от ошибок Telegram API при изменении текста
            try:
                await call.message.edit_text(
                    build_lose_text(call.from_user.mention_html(), bet, int(bet * mult_could), emojis["lose"]),
                    reply_markup=get_keyboard(revealed, owner_id, True, field), parse_mode="HTML"
                )
            except Exception:
                pass
        else:  # АЛМАЗ
            mult = round(MULTIPLIER_STEP ** len(revealed), 2)
            await db.execute(
                "UPDATE mine_games SET revealed_cells = ?, last_action = CURRENT_TIMESTAMP WHERE user_id = ? AND chat_id = ?",
                (json.dumps(revealed), owner_id, call.message.chat.id)
            )
            await db.commit()

            # Сначала отвечаем Telegram!
            try:
                await call.answer(f"💎 +1! x{mult}")
            except Exception:
                pass

            # Защита от ошибок Telegram API при изменении текста
            try:
                await call.message.edit_text(
                    f"{call.from_user.mention_html()}, игра идёт...\n\n<blockquote expandable>"
                    f"📈 Множитель: x{mult}\n💵 Выигрыш: {fmt_num(int(bet * mult))} dC\n💎 Алмазов: {len(revealed)}</blockquote>",
                    reply_markup=get_keyboard(revealed, owner_id, False, field), parse_mode="HTML"
                )
            except Exception:
                pass


@router.callback_query(F.data.startswith("mcash_"))
async def cashout(call: CallbackQuery):
    user_id = call.from_user.id
    current_time = time.time()

    # ПРОВЕРКА АНТИФЛУДА
    if user_id in last_clicks and current_time - last_clicks[user_id] < FLOOD_TIMEOUT:
        return await call.answer("Не так быстро! ⏳", show_alert=False)
    last_clicks[user_id] = current_time

    owner_id = int(call.data.split("_")[1])
    if user_id != owner_id:
        return await call.answer("Вы не можете забрать чужой выигрыш!", show_alert=True)

    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        async with db.execute(
                "SELECT bet, mines_map, revealed_cells, message_id FROM mine_games WHERE user_id = ? AND chat_id = ?",
                (owner_id, call.message.chat.id)
        ) as cur:
            row = await cur.fetchone()

        if not row or call.message.message_id != row[3]:
            return await call.answer("Игра уже завершена!", show_alert=True)

        bet, field_json, revealed_json, _ = row
        revealed = json.loads(revealed_json)
        if not revealed:
            return await call.answer("Откройте хотя бы один алмаз!", show_alert=True)

        mult = round(MULTIPLIER_STEP ** len(revealed), 2)
        win_amount = int(bet * mult)

        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (win_amount, f"@{owner_id}"))
        await db.execute("DELETE FROM mine_games WHERE user_id = ? AND chat_id = ?", (owner_id, call.message.chat.id))
        await db.commit()

        # 1. Сначала отвечаем Telegram, что всё ок
        try:
            await call.answer(f"Выигрыш {fmt_num(win_amount)} зачислен!", show_alert=True)
        except Exception:
            pass

        # 2. Потом обновляем текст (с защитой от ошибок Telegram)
        try:
            emojis = await get_emojis(db)
            max_win = int(bet * round(MULTIPLIER_STEP ** (GRID_SIZE - MINES_COUNT), 2))
            await call.message.edit_text(
                build_cashout_text(call.from_user.mention_html(), win_amount, max_win, emojis["cashout"]),
                reply_markup=get_keyboard(revealed, owner_id, True, json.loads(field_json)),
                parse_mode="HTML"
            )
        except Exception:
            pass  # Если не удалось отредактировать из-за лимитов — не страшно, деньги уже выданы


@router.callback_query(F.data.startswith("mquit_"))
async def quit_game(call: CallbackQuery):
    user_id = call.from_user.id
    current_time = time.time()

    # ПРОВЕРКА АНТИФЛУДА
    if user_id in last_clicks and current_time - last_clicks[user_id] < FLOOD_TIMEOUT:
        return await call.answer("Не так быстро! ⏳", show_alert=False)
    last_clicks[user_id] = current_time

    owner_id = int(call.data.split("_")[1])
    if user_id != owner_id:
        return await call.answer("Вы не можете отменить чужую игру!", show_alert=True)

    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        async with db.execute(
                "SELECT bet, mines_map, revealed_cells, message_id FROM mine_games WHERE user_id = ? AND chat_id = ?",
                (owner_id, call.message.chat.id)
        ) as cur:
            row = await cur.fetchone()

        if not row or call.message.message_id != row[3]:
            return await call.answer("Игра не найдена!", show_alert=True)

        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (row[0], f"@{owner_id}"))
        await db.execute("DELETE FROM mine_games WHERE user_id = ? AND chat_id = ?", (owner_id, call.message.chat.id))
        await db.commit()

        try:
            await call.answer(f"Игра отменена. Возвращено {fmt_num(row[0])} dC.", show_alert=True)
        except Exception:
            pass

        try:
            await call.message.edit_text(
                build_cancel_text(call.from_user.mention_html()),
                reply_markup=get_keyboard(json.loads(row[2]), owner_id, True, json.loads(row[1])),
                parse_mode="HTML"
            )
        except Exception:
            pass


# ─── ADMIN: /ckn ─────────────────────────────────────────────────────────────

EMOJI_ALIASES = {
    "проигрыш": "lose", "lose": "lose",
    "победа": "win", "win": "win",
    "забрал": "cashout", "cashout": "cashout",
}


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.lower().startswith("/ckn "))
async def cmd_ckn(message: Message):
    member = await message.chat.get_member(message.from_user.id)
    if message.from_user.id not in ADMIN_IDS and member.status not in ("administrator", "creator"):
        return await message.reply("❌ У вас нет прав.")

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3: return await message.reply("Использование: /ckn <тип> <эмодзи>")

    key_short = EMOJI_ALIASES.get(parts[1].lower())
    if not key_short: return await message.reply("Типы: проигрыш, победа, забрал")

    new_emoji = parts[2].strip()
    if message.entities:
        for ent in message.entities:
            if ent.type == "custom_emoji":
                new_emoji = f'<tg-emoji emoji-id="{ent.custom_emoji_id}">{ent.extract_from(message.text)}</tg-emoji>'
                break

    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute(
            "INSERT INTO mine_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (f"emoji_{key_short}", new_emoji))
        await db.commit()

    await message.reply(f"✅ Эмодзи обновлён: {new_emoji}", parse_mode="HTML")
