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
CHANNEL_ID = -1003433963320
CHANNEL_URL = "https://t.me/vorneblablabla"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

async def is_subscribed(user_id: int):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

@dp.message(Command("start"))
async def start(message: types.Message):
    if await is_subscribed(message.from_user.id):
        await message.answer(f"✅ Ты уже с нами! Переходи в канал: {CHANNEL_URL}")
    else:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_URL))
        builder.row(types.InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check"))
        
        await message.answer(
            "👋 Привет! Чтобы получить доступ к программе, подпишись на мой канал. Apk приложения находится там!"
            "Релиз и все новости будут только там!",
            reply_markup=builder.as_markup()
        )

@dp.callback_query(F.data == "check")
async def check_callback(callback: types.CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_text(f"🚀 Красава! Твой доступ открыт. Переходи: {CHANNEL_URL}")
    else:
        await callback.answer("❌ Сначала подпишись на канал!", show_alert=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
