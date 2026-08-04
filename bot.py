import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command

# ============ КОНФИГУРАЦИЯ ============
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден! Добавьте переменную BOT_TOKEN в Railway.")

# ============ ХРАНИЛИЩЕ В ПАМЯТИ ============
waiting_queue = set()
active_chats = {}

# ============ КЛАВИАТУРЫ ============
def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔍 Найти собеседника")]],
        resize_keyboard=True
    )

def chat_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Завершить чат")]],
        resize_keyboard=True
    )

def after_chat_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Найти собеседника")],
            [KeyboardButton(text="🏠 В меню")]
        ],
        resize_keyboard=True
    )

# ============ ИНИЦИАЛИЗАЦИЯ ============
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ============ ОБРАБОТЧИКИ ============

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    if user_id in active_chats:
        await message.answer("Вы уже в чате. Нажмите «Завершить чат» сначала.")
        return
    waiting_queue.discard(user_id)
    await message.answer(
        "👋 Добро пожаловать в анонимный чат!\n\n"
        "Нажмите кнопку ниже, чтобы найти собеседника.",
        reply_markup=main_kb()
    )

@dp.message(F.text == "🔍 Найти собеседника")
async def find_partner(message: Message):
    user_id = message.from_user.id
    if user_id in active_chats:
        await message.answer("Вы уже общаетесь. Завершите текущий чат сначала.")
        return
    if user_id in waiting_queue:
        await message.answer("Вы уже в очереди. Ожидайте...")
        return

    partner_id = None
    for uid in list(waiting_queue):
        if uid != user_id:
            partner_id = uid
            break

    if partner_id:
        waiting_queue.discard(partner_id)
        active_chats[user_id] = partner_id
        active_chats[partner_id] = user_id
        await message.answer(
            "✅ Собеседник найден! Можете начинать общение.\n\n"
            "Все сообщения будут пересылаться анонимно.",
            reply_markup=chat_kb()
        )
        await bot.send_message(
            partner_id,
            "✅ Собеседник найден! Можете начинать общение.",
            reply_markup=chat_kb()
        )
    else:
        waiting_queue.add(user_id)
        await message.answer(
            "⏳ Ищем собеседника...\n"
            "Как только кто-то подключится — начнём чат!",
            reply_markup=chat_kb()
        )

@dp.message(F.text == "❌ Завершить чат")
async def end_chat(message: Message):
    user_id = message.from_user.id
    if user_id in waiting_queue:
        waiting_queue.discard(user_id)
        await message.answer("❌ Поиск отменён.", reply_markup=main_kb())
        return

    if user_id in active_chats:
        partner_id = active_chats[user_id]
        del active_chats[user_id]
        if partner_id in active_chats:
            del active_chats[partner_id]
        await message.answer("❌ Чат завершён.\n\nЧто дальше?", reply_markup=after_chat_kb())
        await bot.send_message(partner_id, "❌ Собеседник завершил чат.\n\nЧто дальше?", reply_markup=after_chat_kb())
    else:
        await message.answer("Вы не в чате.", reply_markup=main_kb())

@dp.message(F.text == "🏠 В меню")
async def go_menu(message: Message):
    await message.answer("Главное меню", reply_markup=main_kb())

@dp.message(F.content_type.in_({
    "text", "photo", "video", "voice", "audio",
    "document", "sticker", "animation", "video_note"
}))
async def relay_message(message: Message):
    user_id = message.from_user.id
    if user_id in waiting_queue:
        await message.answer("⏳ Подождите, ищем собеседника...")
        return
    if user_id not in active_chats:
        await message.answer("Вы не в чате. Нажмите «Найти собеседника».", reply_markup=main_kb())
        return

    partner_id = active_chats[user_id]
    try:
        await message.copy_to(chat_id=partner_id)
    except Exception as e:
        logging.error(f"Ошибка пересылки: {e}")
        await message.answer("⚠️ Не удалось отправить сообщение.")

# ============ ЗАПУСК ============
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


