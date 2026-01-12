import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

# --- КОНФИГ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Порт для Render или другого хостинга
PORT = int(os.getenv("PORT", 8081))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- HTTP ОБРАБОТЧИКИ ---

async def handle_root(request):
    """Проверка работоспособности (Health Check)"""
    return web.Response(text="Ravell Notification Service is Running", status=200)

async def handle_http_notify(request):
    """
    Принимает POST запрос с JSON:
    {
        "chat_id": 12345678,
        "text": "Ваше сообщение"
    }
    """
    try:
        data = await request.json()
        chat_id = data.get("chat_id")
        text = data.get("text")

        if not chat_id or not text:
            return web.json_response({"error": "Missing chat_id or text"}, status=400)

        await bot.send_message(
            chat_id=chat_id, 
            text=text, 
            parse_mode="HTML"
        )
        logging.info(f"Notification sent to {chat_id}")
        return web.json_response({"status": "ok"})
    
    except Exception as e:
        logging.error(f"Error sending notification: {e}")
        return web.json_response({"error": str(e)}, status=500)

# --- ЗАПУСК ---

async def main():
    # Удаляем вебхук, так как используем polling (или просто запускаем сервер)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Настройка aiohttp сервера
    app = web.Application()
    app.router.add_get('/', handle_root)
    app.router.add_post('/internal/send-notification', handle_http_notify)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    
    logging.info(f"🚀 Notification Server started on port {PORT}...")
    
    # Запускаем одновременно и сервер, и поллинг (если нужно обрабатывать команды в будущем)
    # Если команды вообще не нужны, можно оставить только site.start() и бесконечный цикл
    await asyncio.gather(
        dp.start_polling(bot), 
        site.start()
    )

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")