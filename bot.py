import asyncio
import logging
import sqlite3
import os
from collections import deque
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ChatMemberUpdated
)
from aiogram.filters import Command

# ============ КОНФИГУРАЦИЯ ============
# ВСТАВЬТЕ СЮДА СВОЙ ТОКЕН И ID
BOT_TOKEN = "8943522365:AAFcdcGGA8FKV3GlOLp7kEk4tyt-Qh96s0c"
ADMIN_ID = 8987146035

DB_PATH = "bot.db"

# ============ БАЗА ДАННЫХ ============
def _init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        joined_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS profiles (
        user_id INTEGER PRIMARY KEY,
        gender TEXT,
        age INTEGER,
        registered_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rated_user_id INTEGER,
        reaction TEXT,
        created_at TEXT
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

def _add_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at) VALUES (?, ?, ?, ?)",
              (user_id, username, first_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def _is_banned(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM bans WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def _ban_user(user_id, reason=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO bans (user_id, reason, banned_at) VALUES (?, ?, ?)",
              (user_id, reason, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def _unban_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def _add_report(reporter_id, reported_id, reason=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO reports (reporter_id, reported_id, reason, created_at) VALUES (?, ?, ?, ?)",
              (reporter_id, reported_id, reason, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def _add_reaction(rated_user_id, reaction):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO ratings (rated_user_id, reaction, created_at) VALUES (?, ?, ?)",
              (rated_user_id, reaction, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def _get_user_rating(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT reaction, COUNT(*) FROM ratings WHERE rated_user_id = ? GROUP BY reaction", (user_id,))
    results = c.fetchall()
    conn.close()
    return {row[0]: row[1] for row in results}

def _get_stats():
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

def _is_registered(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM profiles WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def _save_profile(user_id, gender, age):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO profiles (user_id, gender, age, registered_at) VALUES (?, ?, ?, ?)",
              (user_id, gender, age, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# ============ ASYNC ОБЁРТКИ ============
async def init_db():
    await asyncio.to_thread(_init_db)

async def add_user(user_id, username, first_name):
    await asyncio.to_thread(_add_user, user_id, username, first_name)

async def is_banned(user_id):
    return await asyncio.to_thread(_is_banned, user_id)

async def ban_user(user_id, reason=""):
    await asyncio.to_thread(_ban_user, user_id, reason)

async def unban_user(user_id):
    await asyncio.to_thread(_unban_user, user_id)

async def add_report(reporter_id, reported_id, reason=""):
    await asyncio.to_thread(_add_report, reporter_id, reported_id, reason)

async def add_reaction(rated_user_id, reaction):
    await asyncio.to_thread(_add_reaction, rated_user_id, reaction)

async def get_user_rating(user_id):
    return await asyncio.to_thread(_get_user_rating, user_id)

async def get_stats():
    return await asyncio.to_thread(_get_stats)

async def is_registered(user_id):
    return await asyncio.to_thread(_is_registered, user_id)

async def save_profile(user_id, gender, age):
    await asyncio.to_thread(_save_profile, user_id, gender, age)

# ============ ХРАНИЛИЩЕ В ПАМЯТИ ============
waiting_queue = deque()
active_chats = {}
report_pending = set()
registration_state = {}
registration_data = {}
registration_messages = {}

_chat_lock = asyncio.Lock()

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

def gender_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👩 Девушка", callback_data="gender_female")],
            [InlineKeyboardButton(text="👨 Парень", callback_data="gender_male")]
        ]
    )

def reaction_kb(partner_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️", callback_data=f"react:❤️:{partner_id}"),
                InlineKeyboardButton(text="🔥", callback_data=f"react:🔥:{partner_id}"),
                InlineKeyboardButton(text="🤡", callback_data=f"react:🤡:{partner_id}"),
                InlineKeyboardButton(text="💩", callback_data=f"react:💩:{partner_id}"),
            ]
        ]
    )

# ============ ИНИЦИАЛИЗАЦИЯ ============
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.message.filter(F.chat.type == "private")
dp.edited_message.filter(F.chat.type == "private")
dp.callback_query.filter(F.message.chat.type == "private")

# ============ ХЕЛПЕРЫ ============
async def safe_delete_messages(user_id, msg_ids):
    for msg_id in msg_ids:
        try:
            await bot.delete_message(user_id, msg_id)
        except Exception:
            pass

async def auto_delete_message(chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass

async def clear_registration(user_id):
    await safe_delete_messages(user_id, registration_messages.pop(user_id, []))
    registration_state.pop(user_id, None)
    registration_data.pop(user_id, None)
    registration_messages.pop(user_id, None)

async def start_registration(message: Message):
    user_id = message.from_user.id
    registration_state[user_id] = "awaiting_gender"
    registration_messages[user_id] = []
    registration_data.pop(user_id, None)
    msg = await message.answer(
        "📋 Добро пожаловать!\n\n"
        "Для начала необходимо пройти короткую регистрацию.\n\n"
        "1️⃣ Выберите ваш пол:",
        reply_markup=gender_kb()
    )
    registration_messages[user_id].append(msg.message_id)

# ============ ОБРАБОТЧИКИ ============

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id

    if await is_banned(user_id):
        await message.answer("🚫 Вы заблокированы в этом боте.")
        return

    await add_user(user_id, message.from_user.username, message.from_user.first_name)

    async with _chat_lock:
        if user_id in active_chats:
            await message.answer("Вы уже в чате. Нажмите «Завершить чат» сначала.")
            return
        try:
            waiting_queue.remove(user_id)
        except ValueError:
            pass
        report_pending.discard(user_id)

    if not await is_registered(user_id):
        await start_registration(message)
        return

    await message.answer(
        "👋 Добро пожаловать в анонимный чат!\n\n"
        "🔒 Оригинальный и самый популярный Анонимный чат в Телеграме!\n\n"
        "💬 Общайся анонимно с случайными собеседниками.\n\n"
        "🔞 Чат строго 18+\n\n"
        "🔍 Нажмите кнопку ниже, чтобы найти собеседника.",
        reply_markup=main_kb()
    )

@dp.callback_query(F.data.startswith("gender_"))
async def process_gender(callback: CallbackQuery):
    user_id = callback.from_user.id
    if registration_state.get(user_id) != "awaiting_gender":
        await callback.answer()
        return

    gender = "female" if callback.data == "gender_female" else "male"
    gender_text = "👩 Девушка" if gender == "female" else "👨 Парень"
    registration_data[user_id] = {"gender": gender}

    try:
        await callback.message.delete()
    except Exception:
        pass

    registration_state[user_id] = "awaiting_age"
    msg = await bot.send_message(
        user_id,
        f"✅ Пол: {gender_text}\n\n"
        f"2️⃣ Укажите ваш возраст (цифрами):\n\n"
        f"🔞 Доступ разрешён только с 18 лет!",
        reply_markup=cancel_kb()
    )
    registration_messages[user_id].append(msg.message_id)
    await callback.answer()

@dp.message(F.text == "❌ Отмена")
async def cancel_registration(message: Message):
    user_id = message.from_user.id
    try:
        await message.delete()
    except Exception:
        pass
    await clear_registration(user_id)
    msg = await message.answer("❌ Регистрация отменена. Нажмите /start чтобы начать заново.")
    asyncio.create_task(auto_delete_message(user_id, msg.message_id, 5))

@dp.message(F.text.regexp(r"^\d+$"))
async def process_age(message: Message):
    user_id = message.from_user.id
    if registration_state.get(user_id) != "awaiting_age":
        return

    age = int(message.text)
    try:
        await message.delete()
    except Exception:
        pass

    await clear_registration(user_id)

    if age < 18:
        msg = await message.answer(
            "🚫 Доступ запрещён!\n\n"
            f"Вам указано {age} лет. Данный чат строго 18+.\n\n"
            "Вы не можете использовать этого бота."
        )
        return

    gender = registration_data.pop(user_id, {}).get("gender", "unknown")
    await save_profile(user_id, gender, age)
    registration_state.pop(user_id, None)

    gender_text = "👩" if gender == "female" else "👨"
    msg = await message.answer(
        f"✅ Регистрация завершена!\n\n"
        f"{gender_text} Пол: {'Девушка' if gender == 'female' else 'Парень'}\n"
        f"🎂 Возраст: {age}\n\n"
        f"🔍 Нажмите кнопку ниже, чтобы найти собеседника.",
        reply_markup=main_kb()
    )
    asyncio.create_task(auto_delete_message(user_id, msg.message_id, 10))

@dp.message(F.text == "🔍 Найти собеседника")
async def find_partner(message: Message):
    user_id = message.from_user.id

    if not await is_registered(user_id):
        await message.answer("📋 Сначала пройдите регистрацию. Нажмите /start")
        return

    if await is_banned(user_id):
        await message.answer("🚫 Вы заблокированы.")
        return

    async with _chat_lock:
        if user_id in active_chats:
            await message.answer("Вы уже общаетесь. Завершите текущий чат сначала.")
            return
        if user_id in waiting_queue:
            await message.answer("Вы уже в очереди. Ожидайте...")
            return

        partner_id = None
        while waiting_queue:
            candidate = waiting_queue.popleft()
            if candidate == user_id:
                continue
            if await is_banned(candidate) or candidate in active_chats:
                continue

            rating = await get_user_rating(user_id)
            rating_text = ""
            if rating:
                total = sum(rating.values())
                if total > 0:
                    rating_text = f"\n\n📊 Рейтинг собеседника: "
                    for emoji, count in sorted(rating.items(), key=lambda x: x[1], reverse=True):
                        rating_text += f"{emoji} {count}  "
                    rating_text += f"(всего {total})"

            try:
                await bot.send_message(
                    candidate,
                    f"✅ Собеседник найден!{rating_text}\n\nМожете начинать общение.",
                    reply_markup=chat_kb()
                )
            except Exception:
                continue

            active_chats[user_id] = candidate
            active_chats[candidate] = user_id

            rating = await get_user_rating(candidate)
            rating_text = ""
            if rating:
                total = sum(rating.values())
                if total > 0:
                    rating_text = f"\n\n📊 Рейтинг собеседника: "
                    for emoji, count in sorted(rating.items(), key=lambda x: x[1], reverse=True):
                        rating_text += f"{emoji} {count}  "
                    rating_text += f"(всего {total})"

            try:
                await message.answer(
                    f"✅ Собеседник найден!{rating_text}\n\n"
                    f"Можете начинать общение.\n\n"
                    f"Все сообщения пересылаются анонимно.\n\n"
                    f"⏭ — сменить собеседника\n"
                    f"🚨 — пожаловаться на нарушение\n"
                    f"❌ — завершить чат",
                    reply_markup=chat_kb()
                )
            except Exception:
                active_chats.pop(user_id, None)
                active_chats.pop(candidate, None)
                waiting_queue.appendleft(candidate)
                try:
                    await bot.send_message(candidate, "❌ Собеседник недоступен. Попробуйте найти нового.", reply_markup=main_kb())
                except Exception:
                    pass
                return
            partner_id = candidate
            break

        if not partner_id:
            waiting_queue.append(user_id)
            await message.answer(
                "⏳ Ищем собеседника...\n"
                "Как только кто-то подключится — начнём чат!",
                reply_markup=chat_kb()
            )

async def disconnect_pair(user_id, notify=True):
    partner_id = None
    async with _chat_lock:
        try:
            waiting_queue.remove(user_id)
        except ValueError:
            pass
        report_pending.discard(user_id)

        partner_id = active_chats.get(user_id)
        if partner_id is None:
            return None

        active_chats.pop(user_id, None)
        active_chats.pop(partner_id, None)
        report_pending.discard(partner_id)

    for uid, other_id in [(user_id, partner_id), (partner_id, user_id)]:
        try:
            await bot.send_message(uid, "👤 Оцените собеседника:", reply_markup=reaction_kb(other_id))
        except Exception:
            pass

    if notify and partner_id:
        try:
            await bot.send_message(
                partner_id,
                "❌ Собеседник завершил чат.\n\nЧто дальше?",
                reply_markup=after_chat_kb()
            )
        except Exception:
            pass

    return partner_id

@dp.callback_query(F.data.startswith("react:"))
async def process_reaction(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return

    reaction = parts[1]
    rated_id = int(parts[2])
    user_id = callback.from_user.id

    if user_id == rated_id:
        await callback.answer("❌ Нельзя оценить самого себя!")
        return

    await add_reaction(rated_id, reaction)
    try:
        await callback.message.edit_text(
            f"✅ Вы поставили реакцию {reaction}\n\n"
            f"Спасибо за обратную связь!"
        )
    except Exception:
        pass
    await callback.answer()

@dp.message(F.text == "❌ Завершить чат")
async def end_chat(message: Message):
    user_id = message.from_user.id
    report_pending.discard(user_id)

    async with _chat_lock:
        in_queue = user_id in waiting_queue
        in_chat = user_id in active_chats

    if in_queue:
        async with _chat_lock:
            try:
                waiting_queue.remove(user_id)
            except ValueError:
                pass
        await message.answer("❌ Поиск отменён.", reply_markup=main_kb())
        return

    if in_chat:
        await disconnect_pair(user_id, notify=True)
        await message.answer("❌ Чат завершён.\n\nЧто дальше?", reply_markup=after_chat_kb())
    else:
        await message.answer("Вы не в чате.", reply_markup=main_kb())

@dp.message(F.text == "⏭ Следующий собеседник")
async def next_partner(message: Message):
    user_id = message.from_user.id

    if not await is_registered(user_id):
        await message.answer("📋 Сначала пройдите регистрацию. Нажмите /start")
        return

    async with _chat_lock:
        in_chat = user_id in active_chats
        in_queue = user_id in waiting_queue

    if in_chat:
        await disconnect_pair(user_id, notify=True)
        await message.answer("⏭ Ищем нового собеседника...", reply_markup=main_kb())
        await find_partner(message)
    elif in_queue:
        await message.answer("⏳ Вы уже в очереди. Ожидайте...")
    else:
        await message.answer("Вы не в чате. Нажмите «Найти собеседника».", reply_markup=main_kb())

@dp.message(F.text == "🚨 Пожаловаться")
async def report_start(message: Message):
    user_id = message.from_user.id
    if user_id not in active_chats:
        await message.answer("Вы не в чате. Некого жаловаться.", reply_markup=main_kb())
        return
    report_pending.add(user_id)
    await message.answer(
        "🚨 Опишите нарушение одним сообщением.\n"
        "Например: спам, оскорбления, нежелательный контент.\n\n"
        "Нажмите «Отмена», чтобы отменить.",
        reply_markup=cancel_kb()
    )

@dp.message(F.text == "🏠 В меню")
async def go_menu(message: Message):
    user_id = message.from_user.id
    async with _chat_lock:
        try:
            waiting_queue.remove(user_id)
        except ValueError:
            pass
        report_pending.discard(user_id)
        in_chat = user_id in active_chats

    if in_chat:
        await disconnect_pair(user_id, notify=True)
    await message.answer("Главное меню", reply_markup=main_kb())

# ============ АДМИН-КОМАНДЫ ============

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Эта команда только для администратора.")
        return

    total_users, total_bans, total_reports = await get_stats()
    async with _chat_lock:
        chats = len(active_chats) // 2
        queue = len(waiting_queue)

    await message.answer(
        f"📊 Статистика:\n\n"
        f"👤 Пользователей: {total_users}\n"
        f"🚫 Заблокировано: {total_bans}\n"
        f"🚨 Жалоб: {total_reports}\n\n"
        f"🟢 Активных чатов: {chats}\n"
        f"⏳ В очереди: {queue}"
    )

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Эта команда только для администратора.")
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.answer("Использование: /ban id [причина]")
        return

    try:
        user_id = int(args[1])
        reason = args[2] if len(args) > 2 else "Без причины"

        if user_id == ADMIN_ID:
            await message.answer("❌ Нельзя забанить администратора!")
            return

        await ban_user(user_id, reason)

        if user_id in active_chats:
            partner_id = await disconnect_pair(user_id, notify=False)
            if partner_id:
                try:
                    await bot.send_message(
                        partner_id,
                        "❌ Собеседник был заблокирован администратором.",
                        reply_markup=main_kb()
                    )
                except Exception:
                    pass
            try:
                await bot.send_message(
                    user_id,
                    f"🚫 Вы заблокированы администратором.\nПричина: {reason}",
                    reply_markup=main_kb()
                )
            except Exception:
                pass

        await message.answer(f"🚫 Пользователь {user_id} заблокирован.\nПричина: {reason}")
    except ValueError:
        await message.answer("❌ Неверный ID. Использование: /ban 123456789")

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
        await unban_user(user_id)
        try:
            await bot.send_message(
                user_id,
                "✅ Вы были разблокированы администратором.\n"
                "Можете снова пользоваться ботом."
            )
        except Exception:
            pass
        await message.answer(f"✅ Пользователь {user_id} разблокирован.")
    except ValueError:
        await message.answer("❌ Неверный ID. Использование: /unban 123456789")

# ============ ПЕРЕСЫЛКА СООБЩЕНИЙ ============

@dp.message(F.content_type.in_({
    "text", "photo", "video", "voice", "audio",
    "document", "sticker", "animation", "video_note"
}))
async def relay_message(message: Message):
    user_id = message.from_user.id

    if user_id in registration_state:
        return

    if user_id in report_pending:
        reason = message.text or message.caption or "Медиа-сообщение"
        partner_id = active_chats.get(user_id)

        if partner_id:
            await add_report(user_id, partner_id, reason)
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"🚨 Новая жалоба!\n\n"
                    f"От: {user_id}\n"
                    f"На: {partner_id}\n"
                    f"Причина: {reason}\n\n"
                    f"Забанить: /ban {partner_id}"
                )
            except Exception:
                pass
            await message.answer("✅ Жалоба отправлена администратору.", reply_markup=chat_kb())
        else:
            await message.answer("❌ Собеседник уже вышел. Жалоба не отправлена.", reply_markup=main_kb())

        report_pending.discard(user_id)
        return

    if user_id in waiting_queue:
        await message.answer("⏳ Подождите, ищем собеседника...")
        return

    if user_id not in active_chats:
        await message.answer("Вы не в чате. Нажмите «Найти собеседника».", reply_markup=main_kb())
        return

    if await is_banned(user_id):
        await message.answer("🚫 Вы заблокированы.")
        await disconnect_pair(user_id, notify=False)
        return

    partner_id = active_chats[user_id]

    if await is_banned(partner_id):
        await disconnect_pair(user_id, notify=False)
        await message.answer("❌ Ваш собеседник был заблокирован.", reply_markup=main_kb())
        return

    try:
        await message.copy_to(chat_id=partner_id)
    except Exception as e:
        logging.error(f"Ошибка пересылки: {e}")
        await disconnect_pair(user_id, notify=False)
        await message.answer("⚠️ Собеседник недоступен. Чат завершён.", reply_markup=main_kb())

@dp.edited_message()
async def relay_edit(message: Message):
    user_id = message.from_user.id
    if user_id not in active_chats:
        return
    text = message.text or message.caption
    if text:
        try:
            await bot.send_message(active_chats[user_id], f"✏️ {text}")
        except Exception:
            pass

@dp.my_chat_member()
async def my_chat_member_handler(update: ChatMemberUpdated):
    if update.new_chat_member.status in ("kicked", "left"):
        user_id = update.from_user.id
        async with _chat_lock:
            try:
                waiting_queue.remove(user_id)
            except ValueError:
                pass
            report_pending.discard(user_id)
            partner_id = active_chats.pop(user_id, None)
            if partner_id:
                active_chats.pop(partner_id, None)
                report_pending.discard(partner_id)

        if partner_id:
            try:
                await bot.send_message(
                    partner_id,
                    "❌ Собеседник покинул чат.",
                    reply_markup=after_chat_kb()
                )
            except Exception:
                pass

# ============ GRACEFUL SHUTDOWN ============

@dp.shutdown()
async def on_shutdown():
    logging.info("🔌 Завершение работы...")
    async with _chat_lock:
        processed = set()
        for uid, pid in list(active_chats.items()):
            if uid in processed:
                continue
            processed.add(uid)
            processed.add(pid)
            for target in (uid, pid):
                try:
                    await bot.send_message(
                        target,
                        "🔌 Бот перезагружается. Чат завершён.",
                        reply_markup=main_kb()
                    )
                except Exception:
                    pass
        active_chats.clear()
        waiting_queue.clear()
        report_pending.clear()
    await bot.session.close()

# ============ ЗАПУСК ============

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    await init_db()
    logging.info("🚀 Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
