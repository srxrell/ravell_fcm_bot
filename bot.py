import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiohttp import web
import aiohttp

# Конфиг
BOT_TOKEN = os.getenv("BOT_TOKEN")
# URL твоего Go-бэкенда (куда бот сообщит о привязке)
GO_BACKEND_URL = "https://ravell-backend-1.onrender.com/api/v1/tg-bind"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Взаимодействие с Telegram ---

@dp.message(CommandStart(deep_link=True))
async def handler_start(message: types.Message, command: Command):
    args = command.args # Вытаскивает то, что идет после /start
    if args and args.startswith("bind_"):
        user_id = args.replace("bind_", "")
        chat_id = message.chat.id
        
        # Сообщаем бэкенду на Go, что этот юзер теперь связан с этим chat_id
        async with aiohttp.ClientSession() as session:
            payload = {"user_id": int(user_id), "chat_id": chat_id}
            try:
                async with session.post(GO_BACKEND_URL, json=payload) as resp:
                    if resp.status == 200:
                        await message.answer("✅ **Ravell Connected!**\nТеперь уведомления о лайках и ответах будут приходить сюда.")
                    else:
                        await message.answer("❌ Ошибка на сервере привязке. Попробуйте позже.")
            except Exception as e:
                await message.answer("❌ Сервер Ravell недоступен.")

# --- Взаимодействие с Go (Прием уведомлений) ---

async def handle_http_notify(request):
    """Эндпоинт, который дергает Go, чтобы отправить сообщение"""
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
    # Бот слушает порт 8081 (открой его в фаерволе для локального доступа)
    port = os.getenv("PORT")
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    print("🚀 Bot and HTTP Bridge started...")
    await asyncio.gather(
        dp.start_polling(bot),
        site.start()
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())