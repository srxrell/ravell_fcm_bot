import os
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiohttp import web
import aiohttp
import asyncpg
from dotenv import load_dotenv

load_dotenv()

# --- КОНФИГ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
# URL твоего Go-бэкенда (для привязки)
GO_BACKEND_URL = "https://ravell-backend-1.onrender.com/api/v1/tg-bind"
# Строка подключения к базе Neon (для прямой активации премиума)
DATABASE_URL = os.getenv("DATABASE_URL") 

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- 1. /start: Входная точка (Bind + Payment) ---
@dp.message(CommandStart(deep_link=True))
async def handler_start(message: types.Message, command: CommandObject):
    args = command.args
    if not args:
        return

    # === ЛОГИКА ПРИВЯЗКИ (BIND) ===
    if args.startswith("bind_"):
        user_id = args.replace("bind_", "")
        chat_id = message.chat.id
        
        # Сообщаем Go-бэкенду
        async with aiohttp.ClientSession() as session:
            payload = {"user_id": int(user_id), "chat_id": chat_id}
            try:
                async with session.post(GO_BACKEND_URL, json=payload) as resp:
                    if resp.status == 200:
                        await message.answer("✅ <b>Ravell Connected!</b>\nТеперь уведомления приходят сюда.", parse_mode="HTML")
                    else:
                        await message.answer("❌ Ошибка привязки.")
            except Exception:
                await message.answer("❌ Сервер недоступен.")

    # === ЛОГИКА ОПЛАТЫ (SUB) ===
    elif args.startswith("sub_"):
        # Пример: sub_pro_123
        parts = args.split("_")
        if len(parts) < 3:
            return
            
        plan = parts[1] # pro
        user_id = parts[2] # 123
        
        if plan == "pro":
            await bot.send_invoice(
                chat_id=message.chat.id,
                title="Ravell Premium",
                description="Активация Premium на 30 дней.\n⭐️ 20 историй в день\n⭐️ Буст в ленте\n⭐️ GIF-аватарка",
                payload=f"pro_{user_id}", # Зашиваем ID юзера
                currency="XTR",           # Telegram Stars
                prices=[LabeledPrice(label="Premium 1 Month", amount=100)], # 100 Звезд
                provider_token=""         # ПУСТОЙ ДЛЯ STARS!
            )

# --- 2. Pre-Checkout (Разрешаем оплату) ---
@dp.pre_checkout_query()
async def pre_checkout_handler(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

# --- 3. SUCCESS: Оплата прошла -> Пишем в БД ---
@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    payment = message.successful_payment
    payload = payment.invoice_payload # "pro_123"
    
    if payload.startswith("pro_"):
        user_id = int(payload.replace("pro_", ""))
        
        # Вычисляем дату: Сейчас + 30 дней
        new_expiry = datetime.now() + timedelta(days=30)
        
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            
            # --- ПРЯМОЙ SQL ЗАПРОС В БАЗУ NEON ---
            await conn.execute("""
                UPDATE users 
                SET premium_until = $1 
                WHERE id = $2
            """, new_expiry, user_id)
            
            await message.answer(
                "🎉 <b>Оплата успешна!</b>\n"
                "Вы стали Premium пользователем. Перезайдите в приложение, чтобы увидеть золотую рамку.",
                parse_mode="HTML"
            )
            print(f"💰 User {user_id} activated Premium via Stars.")
            
        except Exception as e:
            logging.error(f"DB Update Error: {e}")
            await message.answer("Деньги списаны, но база данных не ответила. Сделайте скриншот и пишите в поддержку.")
        finally:
            await conn.close()

# --- Взаимодействие с Go (Прием уведомлений) ---
async def handle_http_notify(request):
    try:
        data = await request.json()
        chat_id = data.get("chat_id")
        text = data.get("text")
        
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        return web.Response(text="OK", status=200)
    except Exception as e:
        return web.Response(text=str(e), status=500)

async def main():
    # Настройка HTTP сервера
    app = web.Application()
    app.router.add_post('/internal/send-notification', handle_http_notify)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = os.getenv("PORT")
    # Если PORT не задан (локально), используем 8081
    if not port:
        port = "8081"
        
    site = web.TCPSite(runner, '0.0.0.0', int(port))
    
    print("🚀 Bot and HTTP Bridge started...")
    
    await asyncio.gather(
        dp.start_polling(bot),
        site.start()
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
