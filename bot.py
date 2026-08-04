import asyncio
import logging
import sqlite3
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.filters import Command

# ============ КОНФИГУРАЦИЯ ============
BOT_TOKEN = "8943522365:AAHSxTCA9OVvDsfHLn_sOo1RD5tifJoYY58"
ADMIN_ID = 8987146035

# ============ БАЗА ДАННЫХ ============
DB_PATH = "bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        joined_at TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id INTEGER,
        reported_id INTEGER,
        reason TEXT,
        created_at TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bans (
        user_id INTEGER PRIMARY KEY,
        reason TEXT,
        banned_at TEXT
    )''')
    
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at) VALUES (?, ?, ?, ?)",
              (user_id, username, first_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM bans WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def ban_user(user_id, reason=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO bans (user_id, reason, banned_at) VALUES (?, ?, ?)",
              (user_id, reason, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def unban_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def add_report(reporter_id, reported_id, reason=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO reports (reporter_id, reported_id, reason, created_at) VALUES (?, ?, ?, ?)",
              (reporter_id, reported_id, reason, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM bans")
    total_bans = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM reports")
    total_reports = c.fetchone()[0]
    conn.close()
    return total_users, total_bans, total_reports

init_db()

# ============ ХРАНИЛИЩЕ В ПАМЯТИ ============
waiting_queue = set()
active_chats = {}
report_pending = {}

# ============ КЛАВИАТУРЫ ============
def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔍 Найти собеседника")]],
        resize_keyboard=True
    )

def chat_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏭ Следующий собеседник")],
            [KeyboardButton(text="🚨 Пожаловаться"), KeyboardButton(text="❌ Завершить чат")]
        ],
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

def cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )

# ============ ИНИЦИАЛИЗАЦИЯ ============
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ============ ОБРАБОТЧИКИ ============

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    
    if is_banned(user_id):
        await message.answer("🚫 Вы заблокированы в этом боте.")
        return
    
    add_user(user_id, message.from_user.username, message.from_user.first_name)
    
    if user_id in active_chats:
        await message.answer("Вы уже в чате. Нажмите «Завершить чат» сначала.")
        return
    
    waiting_queue.discard(user_id)
    report_pending.pop(user_id, None)
    
    welcome_text = (
        "Что умеет этот бот?\n\n"
        "🔒 Оригинальный и самый популярный Анонимный чат в Телеграме!\n\n"
        "💬 Общайся анонимно с случайными собеседниками.\n\n"
        "🔞 Чат строго 18+\n\n"
        "🔍 Для поиска собеседника нажми кнопку внизу экрана"
    )
    
    # Отправляем картинку из файла (должен лежать рядом с bot.py)
    photo = FSInputFile("12983.jpg")
    
    await message.answer_photo(
        photo=photo,
        caption=welcome_text,
        reply_markup=main_kb()
    )

@dp.message(F.text == "🔍 Найти собеседника")
async def find_partner(message: Message):
    user_id = message.from_user.id
    
    if is_banned(user_id):
        await message.answer("🚫 Вы заблокированы.")
        return
    
    if user_id in active_chats:
        await message.answer("Вы уже общаетесь. Завершите текущий чат сначала.")
        return
    
    if user_id in waiting_queue:
        await message.answer("Вы уже в очереди. Ожидайте...")
        return
    
    partner_id = None
    for uid in list(waiting_queue):
        if uid != user_id and not is_banned(uid):
            partner_id = uid
            break
    
    if partner_id:
        waiting_queue.discard(partner_id)
        active_chats[user_id] = partner_id
        active_chats[partner_id] = user_id
        
        await message.answer(
            "✅ Собеседник найден! Можете начинать общение.\n\n"
            "Все сообщения пересылаются анонимно.\n\n"
            "⏭ — сменить собеседника\n"
            "🚨 — пожаловаться на нарушение\n"
            "❌ — завершить чат",
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

async def disconnect_pair(user_id, notify=True):
    waiting_queue.discard(user_id)
    report_pending.pop(user_id, None)
    
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        del active_chats[user_id]
        if partner_id in active_chats:
            del active_chats[partner_id]
        if notify:
            try:
                await bot.send_message(partner_id, "❌ Собеседник завершил чат.\n\nЧто дальше?", reply_markup=after_chat_kb())
            except:
                pass
        return partner_id
    return None

@dp.message(F.text == "❌ Завершить чат")
async def end_chat(message: Message):
    user_id = message.from_user.id
    report_pending.pop(user_id, None)
    
    if user_id in waiting_queue:
        waiting_queue.discard(user_id)
        await message.answer("❌ Поиск отменён.", reply_markup=main_kb())
        return
    
    if user_id in active_chats:
        await disconnect_pair(user_id, notify=True)
        await message.answer("❌ Чат завершён.\n\nЧто дальше?", reply_markup=after_chat_kb())
    else:
        await message.answer("Вы не в чате.", reply_markup=main_kb())

@dp.message(F.text == "⏭ Следующий собеседник")
async def next_partner(message: Message):
    user_id = message.from_user.id
    
    if user_id in active_chats:
        await disconnect_pair(user_id, notify=True)
        await message.answer("⏭ Ищем нового собеседника...", reply_markup=main_kb())
        await find_partner(message)
    elif user_id in waiting_queue:
        await message.answer("⏳ Вы уже в очереди. Ожидайте...")
    else:
        await message.answer("Вы не в чате. Нажмите «Найти собеседника».", reply_markup=main_kb())

@dp.message(F.text == "🚨 Пожаловаться")
async def report_start(message: Message):
    user_id = message.from_user.id
    
    if user_id not in active_chats:
        await message.answer("Вы не в чате. Некого жаловаться.", reply_markup=main_kb())
        return
    
    report_pending[user_id] = True
    await message.answer(
        "🚨 Опишите нарушение одним сообщением.\n"
        "Например: спам, оскорбления, нежелательный контент.\n\n"
        "Нажмите «Отмена», чтобы отменить.",
        reply_markup=cancel_kb()
    )

@dp.message(F.text == "❌ Отмена")
async def cancel_report(message: Message):
    user_id = message.from_user.id
    if user_id in report_pending:
        del report_pending[user_id]
        await message.answer("Жалоба отменена.", reply_markup=chat_kb())
    else:
        await message.answer("Вы не в чате.", reply_markup=main_kb())

@dp.message(F.text == "🏠 В меню")
async def go_menu(message: Message):
    user_id = message.from_user.id
    waiting_queue.discard(user_id)
    report_pending.pop(user_id, None)
    if user_id in active_chats:
        await disconnect_pair(user_id, notify=True)
    await message.answer("Главное меню", reply_markup=main_kb())

# ============ АДМИН-КОМАНДЫ ============

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Эта команда только для администратора.")
        return
    total_users, total_bans, total_reports = get_stats()
    await message.answer(
        f"📊 Статистика:\n\n"
        f"👤 Пользователей: {total_users}\n"
        f"🚫 Заблокировано: {total_bans}\n"
        f"🚨 Жалоб: {total_reports}\n\n"
        f"🟢 Активных чатов: {len(active_chats)//2}\n"
        f"⏳ В очереди: {len(waiting_queue)}"
    )

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Эта команда только для администратора.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /ban id [причина]")
        return
    
    try:
        user_id = int(args[1])
        reason = " ".join(args[2:]) if len(args) > 2 else "Без причины"
        ban_user(user_id, reason)
        
        if user_id in active_chats:
            await disconnect_pair(user_id, notify=True)
            try:
                await bot.send_message(user_id, "🚫 Вы заблокированы администратором.", reply_markup=main_kb())
            except:
                pass
        
        await message.answer(f"🚫 Пользователь {user_id} заблокирован.\nПричина: {reason}")
    except ValueError:
        await message.answer("Неверный ID. Использование: /ban 123456789")

@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Эта команда только для администратора.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /unban id")
        return
    
    try:
        user_id = int(args[1])
        unban_user(user_id)
        await message.answer(f"✅ Пользователь {user_id} разблокирован.")
    except ValueError:
        await message.answer("Неверный ID. Использование: /unban 123456789")

# ============ ПЕРЕСЫЛКА СООБЩЕНИЙ ============

@dp.message(F.content_type.in_({
    "text", "photo", "video", "voice", "audio",
    "document", "sticker", "animation", "video_note"
}))
async def relay_message(message: Message):
    user_id = message.from_user.id
    
    if user_id in report_pending:
        reason = message.text or "Медиа-сообщение"
        partner_id = active_chats.get(user_id)
        
        if partner_id:
            add_report(user_id, partner_id, reason)
            
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"🚨 Новая жалоба!\n\n"
                    f"От: {user_id}\n"
                    f"На: {partner_id}\n"
                    f"Причина: {reason}\n\n"
                    f"Забанить: /ban {partner_id}"
                )
            except:
                pass
            
            await message.answer("✅ Жалоба отправлена администратору.", reply_markup=chat_kb())
        else:
            await message.answer("❌ Собеседник уже вышел. Жалоба не отправлена.", reply_markup=main_kb())
        
        del report_pending[user_id]
        return
    
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

