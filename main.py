import os
import json
import random
import secrets
import datetime
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters
)
from quizzes import quiz_data

load_dotenv()
token = os.getenv("BOT_TOKEN")

USERS_FILE = "users.json"

# Сопоставление внутреннего ключа модуля и его "человеческого" названия
MODULE_TITLES = {
    "module_1": "Базовая теория",
    "module_2": "Backend",
    "module_3": "Frontend",
    "module_mixed": "Случайные вопросы"
}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

users = load_users()
user_data = {}

def get_module_keyboard():
    keyboard = [
        [InlineKeyboardButton("🧠 Модуль 1: Базовая теория", callback_data="module_1")],
        [InlineKeyboardButton("🧩 Модуль 2: Backend", callback_data="module_2")],
        [InlineKeyboardButton("🎨 Модуль 3: Frontend", callback_data="module_3")],
        [InlineKeyboardButton("🎲 Случайные 15 вопросов", callback_data="module_mixed")],
        [InlineKeyboardButton("👤 Профиль", callback_data="profile_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name
    user_id = str(user.id)

    # Инициализация профиля пользователя
    if user_id not in users:
        users[user_id] = {"name": name, "history": []}
        save_users(users)

    greeting = (
        f"Привет, {name}! 👋\n"
        "Я — бот-викторина по ручному тестированию (QA)!\n\n"
        "📚 Как пользоваться ботом?\n"
        "1️⃣ Выбери модуль (базовая теория, backend, frontend или случайные вопросы)\n"
        "2️⃣ Затем выбери тему (подблок)\n"
        "3️⃣ Читай вопрос, жми на вариант ответа (или цифру)\n"
        "4️⃣ После ответа появляется кнопка \"Продолжить\"\n"
        "5️⃣ В конце темы увидишь результат и сможешь пройти тему ещё раз или выбрать другую\n\n"
        "Команда /profile — посмотреть свою историю викторин.\n"
        "Готов учиться и тренироваться? Выбирай модуль ниже 👇"
    )
    if update.message:
        await update.message.reply_text(greeting, reply_markup=get_module_keyboard())
    elif update.callback_query:
        await update.callback_query.edit_message_text(greeting, reply_markup=get_module_keyboard())

async def greet_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data_key = query.data

    # --- Новый блок: обработка профиля
    if data_key == "profile_menu":
        user_id_str = str(user_id)
        if user_id_str not in users or not users[user_id_str].get("history"):
            text = "Профиль пуст. Пройди хотя бы одну тему!"
        else:
            history = users[user_id_str]["history"][-10:]
            text = f"👤 <b>Профиль {users[user_id_str]['name']}</b>\n\n"
            text += f"📚 Пройдено тем: <b>{len(users[user_id_str]['history'])}</b>\n\n"
            for i, item in enumerate(history):
                mod_title = MODULE_TITLES.get(item.get('module', ''), item.get('module', ''))
                text += (f"{i+1}) <b>{mod_title}</b> / <i>{item.get('subblock','')}</i>\n"
                         f"  <b>Результат:</b> {item['score']}/{item['total']} ({item['date'][:19]})\n")
        keyboard = [[InlineKeyboardButton("⬅ Назад", callback_data="restart")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return

    # Случайные 15 вопросов — старт без выбора темы
    if data_key == "module_mixed":
        questions = quiz_data["module_mixed"]["questions"]
        questions = random.sample(questions, min(15, len(questions)))
        user_data[user_id] = {
            "questions": questions,
            "current": 0,
            "score": 0,
            "module": data_key,
            "subblock": "Случайные вопросы",
            "last_quiz": (data_key, "Случайные вопросы")
        }
        await send_question(query, context)
        return

    if data_key == "restart":
        await start(update, context)
        return

    if data_key == "next_question" or data_key.startswith("next|"):
        state = user_data.get(user_id)
        if state is None:
            await query.edit_message_text("Пожалуйста, начни сначала: /start")
            return
        if data_key != f"next|{state.get('turn')}" or not state.get("answered"):
            return
        state["answered"] = False
        state["current"] += 1
        await send_question(query, context)
        return

    if data_key == "repeat_quiz":
        last = user_data.get(user_id, {}).get("last_quiz")
        if last:
            module_key, subblock = last
            if module_key == "module_mixed":
                questions = quiz_data["module_mixed"]["questions"]
                questions = random.sample(questions, min(15, len(questions)))
            else:
                questions = quiz_data[module_key][subblock]["questions"]
            user_data[user_id].update({
                "questions": questions,
                "current": 0,
                "score": 0,
                "module": module_key,
                "subblock": subblock
            })
            await send_question(query, context)
        else:
            await start(update, context)
        return

    # Тема (подблок) по индексу
    if "|" in data_key:
        module_key, subblock_idx = data_key.split("|", 1)
        subblocks = list(quiz_data[module_key].keys())
        subblock = subblocks[int(subblock_idx)]
        questions = quiz_data[module_key][subblock]["questions"]
        user_data[user_id] = {
            "questions": questions,
            "current": 0,
            "score": 0,
            "module": module_key,
            "subblock": subblock,
            "last_quiz": (module_key, subblock)
        }
        await send_question(query, context)
        return

    # Выбор модуля (без случайных) — показать подблоки
    if data_key in quiz_data:
        subblocks = list(quiz_data[data_key].keys())
        keyboard = [
            [InlineKeyboardButton(subblock, callback_data=f"{data_key}|{i}")]
            for i, subblock in enumerate(subblocks)
        ]
        keyboard.append([InlineKeyboardButton("🔙 Вернуться к модулям", callback_data="restart")])
        await query.edit_message_text("Выбери тему:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    await query.edit_message_text("❌ Неверный выбор. Попробуйте снова.", reply_markup=get_module_keyboard())

async def send_question(query, context):
    data = user_data[query.from_user.id]
    current_index = max(0, min(data.get("current", 0), len(data.get("questions", []))))
    questions = data["questions"]

    if current_index < len(questions):
        turn = secrets.token_hex(8)
        data.update(turn=turn, answered=False)
        q = questions[current_index]
        options_text = "\n".join([f"{i + 1}. {opt}" for i, opt in enumerate(q["options"])])
        text = f"Вопрос {current_index + 1}: {q['question']}\n\n{options_text}"

        answer_buttons = [
            InlineKeyboardButton(str(i + 1), callback_data=f"answer|{turn}|{i}")
            for i in range(len(q["options"]))
        ]
        keyboard = [answer_buttons]
        keyboard.append([
            InlineKeyboardButton("🏠 Модули", callback_data="restart")
        ])
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        name = users.get(str(query.from_user.id), {}).get("name", "пользователь")
        score = data["score"]
        total = len(questions)
        keyboard = [
            [InlineKeyboardButton("🔄 Пройти ещё раз", callback_data="repeat_quiz")],
            [InlineKeyboardButton("🏠 К выбору модуля", callback_data="restart")]
        ]
        await query.edit_message_text(
            text=f"🏁 {name}, тема завершена!\nРезультат: {score}/{total}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        # Сохраняем результат в профиль пользователя
        user_id_str = str(query.from_user.id)
        history = users[user_id_str].setdefault("history", [])
        history.append({
            "date": str(datetime.datetime.now()),
            "module": data["module"],
            "subblock": data.get("subblock", ""),
            "score": score,
            "total": total
        })
        save_users(users)

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id not in user_data:
        await query.edit_message_text("Пожалуйста, начни сначала: /start")
        return

    data = user_data[user_id]
    parts = query.data.split("|")
    if len(parts) != 3 or parts[1] != data.get("turn") or data.get("answered"):
        return
    if data["current"] >= len(data["questions"]):
        return
    current_question = data["questions"][data["current"]]
    if parts[2] not in map(str, range(len(current_question["options"]))):
        return
    index = int(parts[2])
    data["answered"] = True
    next_button = InlineKeyboardButton("➡️ Продолжить", callback_data=f"next|{parts[1]}")
    correct = current_question["correct"]

    if index in correct:
        data["score"] += 1
        await query.edit_message_text(
            text="✅ Верно!",
            reply_markup=InlineKeyboardMarkup([[next_button]])
        )
    else:
        correct_texts = [current_question["options"][i] for i in correct]
        correct_str = " / ".join(correct_texts)
        await query.edit_message_text(
            text=f"❌ Неверно. Правильный ответ: {correct_str}",
            reply_markup=InlineKeyboardMarkup([[next_button]])
        )

def main():
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^привет"), greet_user))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^answer\|"))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("✅ Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
