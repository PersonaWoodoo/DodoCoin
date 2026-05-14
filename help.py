from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

router = Router()


# ---------------------------------------------------------------------------
# Клавиатуры
# ---------------------------------------------------------------------------

def get_help_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎮 Игры",     callback_data="help_games_menu"),
            InlineKeyboardButton(text="📜 Команды",  callback_data="help_cmds"),
        ]
    ])

def get_help_games_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎰 Рулетка", callback_data="help_game_roulette"),
            InlineKeyboardButton(text="💣 Мины",    callback_data="help_game_mines"),
        ],
        [
            InlineKeyboardButton(text="🚀 Краш",    callback_data="help_game_crash"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="help_main")],
    ])

def get_back_kb(target: str = "help_main"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=target)]
    ])


# ---------------------------------------------------------------------------
# Тексты
# ---------------------------------------------------------------------------

TEXT_MAIN = "❓ <b>Справочник по боту</b>\n\nВыберите интересующий раздел ниже:"

TEXT_GAMES_MENU = "<b>🎮 Доступные игры</b>\n\nВыберите игру ниже, чтобы узнать правила и как делать ставки:"

TEXT_GAME_ROULETTE = (
    "<b>🎰 Игра: Рулетка</b>\n\n"
    "<b>Типы ставок:</b>\n"
    "• <code>5000 к</code> — ставка на красное\n"
    "• <code>5000 ч</code> — ставка на черное\n"
    "• <code>5000 10</code> — ставка на точное число\n"
    "• <code>5000 10-36</code> — ставка на диапазон чисел\n"
    "• <code>5000 одд</code> / <code>евен</code> — ставка на четное/нечетное"
)

TEXT_GAME_MINES = (
    "<b>💣 Игра: Мины</b>\n\n"
    "Классическая игра в сапера. Чем больше мин обходите, тем выше множитель!\n\n"
    "<b>Как играть:</b>\n"
    "Ставка: <code>мины 500</code>"
)

TEXT_GAME_CRASH = (
    "<b>🚀 Игра: Краш</b>\n\n"
    "График растет, а вместе с ним и ваш выигрыш. Главное — успеть забрать деньги до того, как он обвалится!\n\n"
    "<b>Как играть:</b>\n"
    "Ставка и автовывод: <code>краш 5000 1.2</code>"
)

TEXT_CMDS = (
    "<b>📜 Основные команды:</b>\n\n"
    "• <code>/top</code> — топ пользователей по балансу\n"
    "• <code>п 100 реп</code> — передача валюты в ответ на сообщение\n"
    "• <code>/seting</code> — настройка игр в вашей группе (только для админов)"
)


# ---------------------------------------------------------------------------
# Хендлеры
# ---------------------------------------------------------------------------

@router.message(F.text.lower().in_({"игры", "помощь", "команды", "❓ помощь"}))
async def cmd_help(message: Message):
    await message.answer(TEXT_MAIN, reply_markup=get_help_main_kb(), parse_mode="HTML")


@router.callback_query(F.data == "help_main")
async def call_help_main(call: CallbackQuery):
    await call.message.edit_text(TEXT_MAIN, reply_markup=get_help_main_kb(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "help_cmds")
async def call_help_cmds(call: CallbackQuery):
    await call.message.edit_text(TEXT_CMDS, reply_markup=get_back_kb(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "help_games_menu")
async def call_help_games_menu(call: CallbackQuery):
    await call.message.edit_text(TEXT_GAMES_MENU, reply_markup=get_help_games_kb(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "help_game_roulette")
async def call_help_game_roulette(call: CallbackQuery):
    await call.message.edit_text(TEXT_GAME_ROULETTE, reply_markup=get_back_kb("help_games_menu"), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "help_game_mines")
async def call_help_game_mines(call: CallbackQuery):
    await call.message.edit_text(TEXT_GAME_MINES, reply_markup=get_back_kb("help_games_menu"), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "help_game_crash")
async def call_help_game_crash(call: CallbackQuery):
    await call.message.edit_text(TEXT_GAME_CRASH, reply_markup=get_back_kb("help_games_menu"), parse_mode="HTML")
    await call.answer()
