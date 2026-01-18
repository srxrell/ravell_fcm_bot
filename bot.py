import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()

# --- КОНФИГ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = -1003433963320
CHANNEL_URL = "https://t.me/vorneblablabla"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ПРОВЕРКА ПОДПИСКИ ---
async def is_subscribed(user_id: int):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# --- START ---
@dp.message(Command("start"))
async def start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_URL))
    builder.row(types.InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check"))
    builder.row(types.InlineKeyboardButton(text="⭐ Поддержать донатом", callback_data="donate"))
   
    await message.answer(
        "👋 Привет! Чтобы получить доступ к программе, подпишись на мой канал.\n"
        "Apk приложения находится там! Релиз и все новости будут только там!",
        reply_markup=builder.as_markup()
    )

# --- ПРОВЕРКА ПОДПИСКИ ---
@dp.callback_query(F.data == "check")
async def check_callback(callback: types.CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_text(
            f"🚀 Красава! Твой доступ открыт. Переходи: {CHANNEL_URL}",
            reply_markup=None
        )
    else:
        await callback.answer("❌ Сначала подпишись на канал!", show_alert=True)

# --- ДОНАТЫ ---
@dp.message(Command("donate"))
@dp.callback_query(F.data == "donate")
async def donate_menu(event: types.Message | types.CallbackQuery):
    text = (
        "💖 Поддержи проект донатом!\n\n"
        "Напиши любое количество звезд, которое хочешь задонатить:\n"
        "Например: `50` или `100`\n\n"
        "Все средства идут на развитие бота и канала 🚀"
    )
    
    if isinstance(event, types.Message):
        await event.answer(text, parse_mode="Markdown")
    else:
        await event.message.edit_text(text, parse_mode="Markdown")
        await event.answer()

# --- ОБРАБОТКА СУММЫ ДОНАТА ---
@dp.message(F.text.regexp(r'^\d+$'))
async def create_invoice(message: types.Message):
    try:
        amount = int(message.text)
        
        if amount < 1:
            await message.answer("❌ Минимум 1 звезда!")
            return
        
        if amount > 2500:
            await message.answer("❌ Максимум 2500 звезд за раз!")
            return
        
        await bot.send_invoice(
            chat_id=message.from_user.id,
            title=f"Донат {amount} ⭐",
            description=f"Поддержка проекта на {amount} звезд Telegram",
            payload=f"donate_{amount}_{message.from_user.id}",
            currency="XTR",
            prices=[types.LabeledPrice(label=f"{amount} звезд", amount=amount)]
        )
        
    except ValueError:
        await message.answer("❌ Введи число!")

# --- ПРЕДЧЕК ПЛАТЕЖА ---
@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

# --- УСПЕШНЫЙ ПЛАТЕЖ ---
@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    payment = message.successful_payment
    transaction_id = payment.telegram_payment_charge_id
    amount = payment.total_amount
    
    logging.info(
        f"💰 Payment: user={message.from_user.id}, "
        f"transaction={transaction_id}, amount={amount}"
    )
    
    await message.answer(
        f"✅ Спасибо за поддержку!\n\n"
        f"💎 Получено: {amount} ⭐\n"
        f"🔖 ID транзакции:\n`{transaction_id}`\n\n"
        f"Если нужен возврат, используй:\n"
        f"/refund `{transaction_id}`",
        parse_mode="Markdown"
    )

# --- ВОЗВРАТ ЗВЕЗД ---
@dp.message(Command("refund"))
async def refund_stars(message: types.Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❌ Укажи ID транзакции!\n\n"
            "Пример:\n"
            "/refund ABC123XYZ\n\n"
            "ID можно найти в сообщении после оплаты."
        )
        return
    
    transaction_id = args[1].strip().replace("`", "")
    
    try:
        await bot.refund_star_payment(
            user_id=message.from_user.id,
            telegram_payment_charge_id=transaction_id
        )
        
        await message.answer(
            "✅ Возврат выполнен успешно!\n"
            f"Звезды вернулись на твой счет 💫"
        )
        logging.info(f"♻️ Refund: user={message.from_user.id}, transaction={transaction_id}")
        
    except Exception as e:
        await message.answer(
            "❌ Ошибка возврата!\n\n"
            "Возможные причины:\n"
            "• Неверный ID транзакции\n"
            "• Возврат уже был выполнен\n"
            "• Прошло более 90 дней\n\n"
            f"Детали: {str(e)}"
        )
        logging.error(f"❌ Refund failed: {e}")

# --- ЗАПУСК ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("🤖 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
