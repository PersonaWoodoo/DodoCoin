from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery
)
import database

router = Router()

# Цены и пакеты
DONATE_PACKS = {
    "p_10":   {"stars": 50,   "amount": 100000,  "bonus": ""},
    "p_50":   {"stars": 100,  "amount": 204000,  "bonus": "+10%"},
    "p_100":  {"stars": 250,  "amount": 525000,  "bonus": "+15%"},
    "p_250":  {"stars": 500,  "amount": 115000,  "bonus": "+20%"},
    "p_500":  {"stars": 1000, "amount": 2300000, "bonus": "+25%"},
    "p_1000": {"stars": 2500, "amount": 6350000, "bonus": "+30%"},
}


# --- ГЛАВНОЕ МЕНЮ ДОНАТА ---
@router.message(F.text == "⭐️ Донат", F.chat.type == "private")
@router.message(F.text == "/donate")
async def cmd_donate(message: Message):
    buttons = []
    for pack_id, data in DONATE_PACKS.items():
        fmt_amount = f"{data['amount']:,}".replace(",", " ")
        bonus_part = f" ({data['bonus']})" if data['bonus'] else ""
        label = f"{data['stars']} ⭐️ - {fmt_amount}{bonus_part}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"pay:unit:{pack_id}")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = "Если возникли проблемы с пополнением обратитесь к\n@debashev"
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# --- ГЕНЕРАЦИЯ СЧЕТА (сразу инвойс, без промежуточного сообщения) ---
@router.callback_query(F.data.startswith("pay:unit:"))
async def create_invoice(call: CallbackQuery, bot: Bot):
    pack_id = call.data.split("pay:unit:")[1]
    if pack_id not in DONATE_PACKS:
        return await call.answer("❌ Товар не найден.", show_alert=True)

    option = DONATE_PACKS[pack_id]
    stars = option["stars"]
    amount = option["amount"]

    fmt_amount = f"{amount:,}".replace(",", " ")
    title = "💳 Пополнение UNIT"
    description = f"Начисление {fmt_amount} UNIT на ваш игровой аккаунт."
    payload = f"unit:{amount}:{stars}"

    try:
        await call.answer()
        await call.message.edit_reply_markup(reply_markup=None)
        await bot.send_invoice(
            chat_id=call.message.chat.id,
            title=title,
            description=description,
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="XTR", amount=stars)]
        )
    except Exception as e:
        print(f"Ошибка при отправке счета: {e}")
        await call.answer("❌ Не удалось создать счет.", show_alert=True)


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


# --- ПОЛУЧЕНИЕ ОПЛАТЫ ---
@router.message(F.successful_payment)
async def on_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    cat, amount, stars = payload.split(":")
    amount = int(amount)
    fmt_amount = f"{amount:,}".replace(",", " ")

    database.log_donate(
        message.from_user.id,
        message.successful_payment.telegram_payment_charge_id,
        amount,
        int(stars)
    )

    await message.answer(
        f"✅ <b>ОПЛАТА ПРОШЛА УСПЕШНО</b>\n\n"
        f"💰 На ваш баланс зачислено: <b>{fmt_amount} UNIT</b>\n"
        f"Спасибо за поддержку проекта!",
        parse_mode="HTML"
    )
