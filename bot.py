import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.enums import ParseMode

# ============ КОНФИГУРАЦИЯ ============
BOT_TOKEN = os.getenv (8943522365:AAHSxTCA9OVvDsfHLn_sOo1RD5tifJoYY58)

# ============ ХРАНИЛИЩЕ В ПАМЯТИ ============
# Очередь пользователей, ожидающих собеседника
waiting_queue = set()

# Активные пары: {user_id: partner_id}
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

# ============ ОБРАБОТЧИКИ КОМАНД ============

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    
    # Если пользователь уже в чате — предупреждаем
    if user_id in active_chats:
        await message.answer("Вы уже в чате. Нажмите «Завершить чат» сначала.")
        return
    
    # Убираем из очереди, если был
    waiting_queue.discard(user_id)
    
    await message.answer(
        "👋 Добро пожаловать в анонимный чат!\n\n"
        "Нажмите кнопку ниже, чтобы найти собеседника.",
        reply_markup=main_kb()
    )

# ============ ПОИСК СОБЕСЕДНИКА ============

@dp.message(F.text == "🔍 Найти собеседника")
@dp.message(F.text == "🔍 Найти ещё")
async def find_partner(message: Message):
    user_id = message.from_user.id
    
    # Проверяем, не в чате ли уже
    if user_id in active_chats:
        await message.answer("Вы уже общаетесь. Завершите текущий чат сначала.")
        return
    
    # Ищем собеседника в очереди
    if user_id in waiting_queue:
        await message.answer("Вы уже в очереди. Ожидайте...")
        return
    
    # Пытаемся найти партнёра
    partner_id = None
    for uid in list(waiting_queue):
        if uid != user_id:
            partner_id = uid
            break
    
    if partner_id:
        # Нашли пару!
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
        # Добавляем в очередь ожидания
        waiting_queue.add(user_id)
        await message.answer(
            "⏳ Ищем собеседника...\n"
            "Как только кто-то подключится — начнём чат!",
            reply_markup=chat_kb()  # Даём возможность отменить
        )

# ============ ЗАВЕРШЕНИЕ ЧАТА ============

@dp.message(F.text == "❌ Завершить чат")
async def end_chat(message: Message):
    user_id = message.from_user.id
    
    # Убираем из очереди, если был в ожидании
    if user_id in waiting_queue:
        waiting_queue.discard(user_id)
        await message.answer(
            "❌ Поиск отменён.",
            reply_markup=main_kb()
        )
        return
    
    # Если в активном чате — разрываем пару
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        
        # Удаляем обоих из активных чатов
        del active_chats[user_id]
        if partner_id in active_chats:
            del active_chats[partner_id]
        
        # Уведомляем обоих
        await message.answer(
            "❌ Чат завершён.\n\nЧто дальше?",
            reply_markup=after_chat_kb()
        )
        await bot.send_message(
            partner_id,
            "❌ Собеседник завершил чат.\n\nЧто дальше?",
            reply_markup=after_chat_kb()
        )
    else:
        await message.answer("Вы не в чате.", reply_markup=main_kb())

@dp.message(F.text == "🏠 В меню")
async def go_menu(message: Message):
    await message.answer("Главное меню", reply_markup=main_kb())

# ============ ПЕРЕСЫЛКА СООБЩЕНИЙ ============

@dp.message(F.content_type.in_({
    "text", "photo", "video", "voice", "audio", 
    "document", "sticker", "animation", "video_note"
}))
async def relay_message(message: Message):
    user_id = message.from_user.id
    
    # Если пользователь в очереди — игнорируем сообщения
    if user_id in waiting_queue:
        await message.answer("⏳ Подождите, ищем собеседника...")
        return
    
    # Если не в чате — предлагаем найти собеседника
    if user_id not in active_chats:
        await message.answer(
            "Вы не в чате. Нажмите «Найти собеседника», чтобы начать.",
            reply_markup=main_kb()
        )
        return
    
    partner_id = active_chats[user_id]
    
    try:
        # Копируем сообщение (без указания оригинального отправителя)
        await message.copy_to(chat_id=partner_id)
    except Exception as e:
        logging.error(f"Ошибка пересылки: {e}")
        await message.answer("⚠️ Не удалось отправить сообщение. Возможно, собеседник заблокировал бота.")

# ============ ЗАПУСК ============

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
