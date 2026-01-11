import os
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiohttp import web
import aiohttp
import asyncpg
from dotenv import load_dotenv

load_dotenv()

# --- КОНФИГ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
# URL твоего Go-бэкенда
GO_BACKEND_URL = "https://ravell-backend-1.onrender.com/api/v1/tg-bind"
# Твоя строка подключения к Neon
DATABASE_URL = os.getenv("DATABASE_URL") 

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- 1. /start: Обработка deep-links (bind_ и sub_) ---
@dp.message(CommandStart())
async def handler_start(message: types.Message, command: CommandObject):
    args = command.args
    
    if not args:
        return await message.answer(
            "👋 <b>Ravell Bot</b> готов к работе.\n\n"
            "Команды для тестов:\n"
            "/pay 10 — создать тестовый счет на 10 звёзд\n"
            "/refund — информация о возвратах",
            parse_mode="HTML"
        )

    # Логика привязки (bind_123)
    if args.startswith("bind_"):
        user_id = args.replace("bind_", "")
        chat_id = message.chat.id
        
        async with aiohttp.ClientSession() as session:
            payload = {"user_id": int(user_id), "chat_id": chat_id}
            try:
                async with session.post(GO_BACKEND_URL, json=payload) as resp:
                    if resp.status == 200:
                        await message.answer("✅ <b>Ravell Connected!</b>\nТеперь уведомления приходят сюда.", parse_mode="HTML")
                    else:
                        await message.answer("❌ Ошибка привязки на стороне бэкенда.")
            except Exception as e:
                logging.error(f"Bind error: {e}")
                await message.answer("❌ Сервер привязки недоступен.")

    # Логика подписки из приложения (sub_pro_123)
    elif args.startswith("sub_"):
        parts = args.split("_")
        if len(parts) >= 3:
            target_user_id = parts[2]
            await bot.send_invoice(
                chat_id=message.chat.id,
                title="Ravell Premium",
                description="Активация Premium на 30 дней.\n⭐️ 20 историй в день\n⭐️ Буст в ленте\n⭐️ GIF-аватарка",
                payload=f"pro_{target_user_id}",
                currency="XTR",
                prices=[LabeledPrice(label="Premium 1 Month", amount=100)],
                provider_token=""
            )

# --- 2. Тестовые команды ---

@dp.message(Command("pay"))
async def cmd_pay(message: types.Message, command: CommandObject):
    amount = 10 # По умолчанию
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

@dp.message(Command("refund"))
async def cmd_refund(message: types.Message):
    await message.answer(
        "ℹ️ <b>Refund System</b>\n\n"
        "Для возврата звёзд бот должен вызвать метод <code>refundStarPayment</code>.\n"
        "Это возможно только если мы сохранили <b>telegram_payment_charge_id</b> после оплаты.",
        parse_mode="HTML"
    )

# --- 3. Обработка платежей (Stars) ---

@dp.pre_checkout_query()
async def pre_checkout_handler(query: PreCheckoutQuery):
    # Одобряем запрос на оплату
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    charge_id = payment.telegram_payment_charge_id
    
    # 1. Если это тестовый платеж
    if payload.startswith("test_"):
        await message.answer(f"✅ Тест пройден!\nID транзакции: <code>{charge_id}</code>", parse_mode="HTML")
        return

    # 2. Если это реальная покупка премиума (pro_123)
    if payload.startswith("pro_"):
        user_id_to_upgrade = int(payload.replace("pro_", ""))
        new_expiry = datetime.now() + timedelta(days=30)
        
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            # Обновляем срок премиума и сохраняем charge_id на случай рефанда
            await conn.execute("""
                UPDATE users 
                SET premium_until = $1 
                WHERE id = $2
            """, new_expiry, user_id_to_upgrade)
            
            await message.answer(
                "🎉 <b>Premium активирован!</b>\nСрок действия: 30 дней.\n"
                "Перезайдите в приложение Ravell.",
                parse_mode="HTML"
            )
            logging.info(f"Payment success for user {user_id_to_upgrade}")
            await conn.close()
        except Exception as e:
            logging.error(f"Database error: {e}")
            await message.answer("⚠️ Оплата прошла, но БД не обновилась. Напишите в поддержку с ID: " + charge_id)

# --- 4. HTTP Bridge (Уведомления от Go) ---

async def handle_http_notify(request):
    try:
        data = await request.json()
        chat_id = data.get("chat_id")
        text = data.get("text")
        
        if chat_id and text:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            return web.Response(text="OK", status=200)
        return web.Response(text="Missing data", status=400)
    except Exception as e:
        return web.Response(text=str(e), status=500)

# --- 5. Запуск ---

async def main():
    # Настройка HTTP моста для бэкенда
    app = web.Application()
    app.router.add_post('/internal/send-notification', handle_http_notify)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv("PORT", 8081))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    logging.info(f"Starting bot and HTTP bridge on port {port}...")
    
    # Запускаем бота и веб-сервер параллельно
    await asyncio.gather(
        dp.start_polling(bot),
        site.start()
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")