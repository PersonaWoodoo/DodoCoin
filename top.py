import aiosqlite
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from database import DB_PATH

router = Router()

BOT_IDS = []  # добавь сюда user_id ботов если нужно исключить


@router.message(Command("top"))
async def cmd_top(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT user_id, name, balance
            FROM users
            WHERE balance > 0
              AND is_bot IS NOT 1
            ORDER BY balance DESC
            LIMIT 30
        """) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        return await message.reply("Список богачей пока пуст!")

    lines = []
    rank = 0
    for user_id, name, balance in rows:
        if user_id in BOT_IDS:
            continue
        rank += 1
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"{rank}.")
        safe_name = name.replace("<", "&lt;").replace(">", "&gt;") if name else "Игрок"
        fmt_balance = f"{balance:,}".replace(",", " ")
        lines.append(f"{medal} {safe_name} — {fmt_balance} dC")

    if not lines:
        return await message.reply("Список богачей пока пуст!")

    response_text = "🏆 ТОП-30 ИГРОКОВ\n\n" + "\n".join(lines)
    await message.answer(response_text, parse_mode=None)
