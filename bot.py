import os
import asyncio
import logging
from datetime import datetime, timedelta
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiohttp import web
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# --- КОНФИГ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
# URL твоего Go-бэкенда (для привязки)
GO_BACKEND_URL = "https://ravell-backend-1.onrender.com/api/v1/tg-bind"
# Строка подключения к базе Neon
DATABASE_URL = os.getenv("DATABASE_URL") 

# ID админа (твой), чтобы только ты видел кнопку возврата при реальной покупке
# Узнай свой ID у @userinfobot и вставь сюда
ADMIN_ID = 7959943536 

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- 1. /start: Входная точка (Bind + Payment) ---
@dp.message(CommandStart(deep_link=True))
async def handler_start(message: types.Message, command: CommandObject):
    args = command.args
    if not args:
        return

    # === BIND (ПРИВЯЗКА) ===
    if args.startswith("bind_"):
        user_id = args.replace("bind_", "")
        chat_id = message.chat.id
        
        async with aiohttp.ClientSession() as session:
            try:
                payload = {"user_id": int(user_id), "chat_id": chat_id}
                async with session.post(GO_BACKEND_URL, json=payload) as resp:
                    if resp.status == 200:
                        await message.answer("✅ <b>Ravell Connected!</b>\nТеперь уведомления приходят сюда.", parse_mode="HTML")
                        # Также дублируем запись в БД напрямую (для надежности)
                        try:
                            conn = await asyncpg.connect(DATABASE_URL)
                            await conn.execute("UPDATE users SET tg_chat_id = $1 WHERE id = $2", chat_id, int(user_id))
                            await conn.close()
                        except:
                            pass
                    else:
                        await message.answer("❌ Ошибка привязки API.")
            except:
                await message.answer("❌ Сервер недоступен.")

    # === SUB (ОПЛАТА ПОДПИСКИ) ===
    elif args.startswith("sub_"):
        # sub_pro_123
        parts = args.split("_")
        if len(parts) >= 3:
            user_id = parts[2]
            
            await bot.send_invoice(
                chat_id=message.chat.id,
                title="Ravell Premium",
                description="Активация Premium на 30 дней.\n⭐️ 20 историй в день\n⭐️ Буст в ленте\n⭐️ GIF-аватарка",
                payload=f"pro_{user_id}",
                currency="XTR",
                prices=[LabeledPrice(label="Premium 1 Month", amount=100)],
                provider_token="" # Пустой для Stars
            )

# --- 2. ТЕСТОВЫЕ КОМАНДЫ ---
@dp.message(Command("pay"))
async def cmd_pay(message: types.Message, command: CommandObject):
    amount = 10
    if command.args and command.args.isdigit():
        amount = int(command.args)
    
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Тестовый платёж",
        description=f"Проверка оплаты Stars на сумму {amount}",
        payload=f"test_{message.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label="Тест", amount=amount)],
        provider_token=""
    )

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        row = await conn.fetchrow("SELECT premium_until FROM users WHERE tg_chat_id = $1", message.chat.id)
        await conn.close()
        
        if row and row['premium_until']:
            await message.answer(f"📅 Ваш Premium до: {row['premium_until']}")
        else:
            await message.answer("У вас нет Premium статуса.")
    except Exception as e:
        await message.answer(f"Ошибка БД: {e}")

# --- 3. ОБРАБОТКА ПЛАТЕЖЕЙ ---
@dp.pre_checkout_query()
async def pre_checkout_handler(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    charge_id = payment.telegram_payment_charge_id
    
    # Кнопка возврата (Refund)
    refund_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Вернуть средства (Refund)", callback_data=f"refund_{charge_id}")]
    ])

    # 1. ТЕСТ
    if payload.startswith("test_"):
        await message.answer(
            f"✅ <b>Тест пройден!</b>\nID: <code>{charge_id}</code>", 
            parse_mode="HTML",
            reply_markup=refund_kb
        )
        return

    # 2. ПОДПИСКА
    if payload.startswith("pro_"):
        user_id_to_upgrade = int(payload.replace("pro_", ""))
        new_expiry = datetime.now() + timedelta(days=30)
        
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute("""
                UPDATE users 
                SET premium_until = $1 
                WHERE id = $2
            """, new_expiry, user_id_to_upgrade)
            await conn.close()
            
            # Показываем кнопку возврата только админу (тебе) или всем (для тестов)
            # Если хочешь для всех во время тестов - оставь как есть
            # Если только для себя: if message.from_user.id == ADMIN_ID: ...
            
            await message.answer(
                "🎉 <b>Premium активирован!</b>\nПерезайдите в приложение.",
                parse_mode="HTML",
                reply_markup=refund_kb # <-- Кнопка возврата добавлена сюда
            )
            logging.info(f"Payment success for user {user_id_to_upgrade}")
            
        except Exception as e:
            logging.error(f"DB Error: {e}")
            await message.answer(f"⚠️ Ошибка БД. ID платежа: {charge_id}", reply_markup=refund_kb)

# --- 4. ЛОГИКА ВОЗВРАТА (REFUND) ---
@dp.callback_query(F.data.startswith("refund_"))
async def refund_handler(callback: CallbackQuery):
    charge_id = callback.data.split("_")[1]
    
    try:
        await bot.refund_star_payment(
            user_id=callback.from_user.id, 
            telegram_payment_charge_id=charge_id
        )
        await callback.message.edit_text(
            f"✅ <b>Возврат выполнен!</b>\nСредства за транзакцию <code>{charge_id}</code> возвращены.",
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"Ошибка возврата: {e}", show_alert=True)

# --- 5. HTTP BRIDGE ---
async def handle_http_notify(request):
    try:
        data = await request.json()
        chat_id = data.get("chat_id")
        text = data.get("text")
        if chat_id and text:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            return web.Response(text="OK", status=200)
        return web.Response(status=400)
    except:
        return web.Response(status=500)

async def main():
    app = web.Application()
    app.router.add_post('/internal/send-notification', handle_http_notify)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv("PORT", 8081))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    print("🚀 Bot started...")
    await asyncio.gather(dp.start_polling(bot), site.start())

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
