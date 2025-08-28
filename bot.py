import os
import random
import string
from datetime import datetime
from typing import Dict, Set

from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not provided")

client = MongoClient(MONGO_URI)
db = client["tg-game"]
users = db["users"]
games = db["games"]

# Ensure each Telegram user ID is stored only once
users.create_index("telegram_id", unique=True)

awaiting_code: Set[int] = set()
pending_kick: Dict[int, str] = {}


async def send_menu(
    chat_id: int, user: Dict, game: Dict, context: ContextTypes.DEFAULT_TYPE
) -> None:
    buttons = [
        [InlineKeyboardButton("Ввести код", callback_data="menu_code")],
        [InlineKeyboardButton("Список противников", callback_data="menu_list")],
    ]
    if is_admin(game, chat_id):
        admin_buttons = []
        if game.get("status") == "waiting":
            admin_buttons.append(InlineKeyboardButton("Начать игру", callback_data="start_game"))
        elif game.get("status") == "running":
            admin_buttons.append(InlineKeyboardButton("Закончить игру", callback_data="end_game"))
        if game.get("status") != "waiting":
            admin_buttons.append(InlineKeyboardButton("Сбросить игру", callback_data="reset_game"))
        if admin_buttons:
            buttons.append(admin_buttons)
    await context.bot.send_message(
        chat_id, "Выберите действие:", reply_markup=InlineKeyboardMarkup(buttons)
    )


def get_name(user: Dict) -> str:
    return "@" + (user.get("username") or user.get("first_name") or "user")


def get_game() -> Dict:
    game = games.find_one()
    if not game:
        game = {"status": "waiting", "admin_ids": ADMIN_IDS}
        games.insert_one(game)
    return game


def is_admin(game: Dict, tg_id: int) -> bool:
    return tg_id in game.get("admin_ids", [])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    users.update_one(
        {"telegram_id": tg_id},
        {
            "$setOnInsert": {
                "telegram_id": tg_id,
                "username": update.effective_user.username,
                "first_name": update.effective_user.first_name,
                "last_name": update.effective_user.last_name,
                "code": code,
                "alive": True,
                "discovered_opponent_ids": [],
            }
        },
        upsert=True,
    )
    user = users.find_one({"telegram_id": tg_id})
    game = get_game()
    if not user.get("alive", True):
        kicker = users.find_one({"_id": user.get("kicked_by")})
        text = f"Игра окончена. Вас выбил {get_name(kicker) if kicker else 'кто-то'}."
        await update.message.reply_text(text)
        return
    if game.get("status") != "running":
        await update.message.reply_text("Игра еще не началась.")
        return
    await send_menu(tg_id, user, game, context)


async def code_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    tg_id = query.from_user.id
    game = get_game()
    user = users.find_one({"telegram_id": tg_id})
    if game.get("status") != "running":
        await context.bot.send_message(tg_id, "Игра еще не началась.")
        if user:
            await send_menu(tg_id, user, game, context)
        return
    if not user or not user.get("alive", True):
        await context.bot.send_message(tg_id, "Игра окончена.")
        return
    awaiting_code.add(tg_id)
    await context.bot.send_message(tg_id, "Отправьте код.")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    if tg_id not in awaiting_code:
        return
    awaiting_code.remove(tg_id)
    code = update.message.text.strip().upper()
    user = users.find_one({"telegram_id": tg_id})
    if not user:
        return
    if code == user.get("code"):
        await update.message.reply_text("Это ваш собственный код!")
        await send_menu(tg_id, user, get_game(), context)
        return
    opponent = users.find_one({"code": code, "alive": True})
    if not opponent:
        await update.message.reply_text("Код не найден.")
        await send_menu(tg_id, user, get_game(), context)
        return
    if opponent["_id"] in user.get("discovered_opponent_ids", []):
        await update.message.reply_text("Уже найден.")
        await send_menu(tg_id, user, get_game(), context)
        return
    users.update_one(
        {"_id": user["_id"]},
        {"$addToSet": {"discovered_opponent_ids": opponent["_id"]}},
    )
    users.update_one(
        {"_id": opponent["_id"]},
        {"$addToSet": {"discovered_opponent_ids": user["_id"]}},
    )
    await update.message.reply_text(f"Вы обнаружили {get_name(opponent)}.")
    await context.bot.send_message(
        opponent["telegram_id"], f"Вы обнаружили {get_name(user)}."
    )
    await send_menu(tg_id, user, get_game(), context)


async def list_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    tg_id = query.from_user.id
    game = get_game()
    user = users.find_one({"telegram_id": tg_id})
    if game.get("status") != "running":
        await context.bot.send_message(tg_id, "Игра еще не началась.")
        if user:
            await send_menu(tg_id, user, game, context)
        return
    if not user or not user.get("alive", True):
        await context.bot.send_message(tg_id, "Игра окончена.")
        return
    ids = user.get("discovered_opponent_ids", [])
    opponents = list(users.find({"_id": {"$in": ids}, "alive": True}))
    if not opponents:
        await context.bot.send_message(tg_id, "Нет доступных противников.")
        await send_menu(tg_id, user, game, context)
        return
    buttons = [
        [InlineKeyboardButton(get_name(o), callback_data=f"kick:{o['_id']}")]
        for o in opponents
    ]
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_menu")])
    await context.bot.send_message(
        tg_id, "Доступные противники:", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    tg_id = query.from_user.id
    user = users.find_one({"telegram_id": tg_id})
    game = get_game()
    if user:
        await send_menu(tg_id, user, game, context)


async def kick_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    opponent_id = query.data.split(":", 1)[1]
    pending_kick[query.from_user.id] = opponent_id
    buttons = [
        [
            InlineKeyboardButton("Да", callback_data="confirm_kick"),
            InlineKeyboardButton("Нет", callback_data="cancel_kick"),
        ]
    ]
    await context.bot.send_message(
        query.from_user.id,
        "Подтвердить выбивание?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def confirm_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    tg_id = query.from_user.id
    opponent_id = pending_kick.get(tg_id)
    if not opponent_id:
        return
    pending_kick.pop(tg_id, None)
    user = users.find_one({"telegram_id": tg_id})
    opponent = users.find_one({"_id": ObjectId(opponent_id)})
    if not user or not opponent:
        await context.bot.send_message(tg_id, "Что-то пошло не так.")
        if user:
            await send_menu(tg_id, user, get_game(), context)
        return
    result = users.update_one(
        {"_id": opponent["_id"], "alive": True},
        {"$set": {"alive": False, "kicked_by": user["_id"]}},
    )
    if result.modified_count == 0:
        await context.bot.send_message(tg_id, "Противник уже выбыл.")
        await send_menu(tg_id, user, get_game(), context)
        return
    await context.bot.send_message(tg_id, f"Вы выбили {get_name(opponent)}.")
    await context.bot.send_message(
        opponent["telegram_id"],
        f"Вас выбил {get_name(user)}. Игра окончена.",
    )
    await send_menu(tg_id, user, get_game(), context)


async def cancel_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    pending_kick.pop(query.from_user.id, None)
    await context.bot.send_message(query.from_user.id, "Отмена.")
    user = users.find_one({"telegram_id": query.from_user.id})
    if user:
        await send_menu(query.from_user.id, user, get_game(), context)


async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    tg_id = query.from_user.id
    game = get_game()
    if not is_admin(game, tg_id):
        return
    if game.get("status") != "waiting":
        await context.bot.send_message(tg_id, "Игра уже началась.")
        user = users.find_one({"telegram_id": tg_id})
        await send_menu(tg_id, user, game, context)
        return
    games.update_one(
        {"_id": game["_id"]},
        {
            "$set": {"status": "running", "started_at": datetime.utcnow(), "ended_at": None}
        },
    )
    users.update_many({}, {"$set": {"discovered_opponent_ids": []}})
    await context.bot.send_message(tg_id, "Игра началась!")
    user = users.find_one({"telegram_id": tg_id})
    await send_menu(tg_id, user, get_game(), context)


async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    tg_id = query.from_user.id
    game = get_game()
    if not is_admin(game, tg_id):
        return
    if game.get("status") != "running":
        await context.bot.send_message(tg_id, "Игра не запущена.")
        user = users.find_one({"telegram_id": tg_id})
        await send_menu(tg_id, user, game, context)
        return
    games.update_one(
        {"_id": game["_id"]},
        {"$set": {"status": "ended", "ended_at": datetime.utcnow()}},
    )
    await context.bot.send_message(tg_id, "Игра завершена.")
    user = users.find_one({"telegram_id": tg_id})
    await send_menu(tg_id, user, get_game(), context)


async def reset_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    tg_id = query.from_user.id
    game = get_game()
    if not is_admin(game, tg_id):
        return
    games.update_one(
        {"_id": game["_id"]},
        {"$set": {"status": "waiting", "started_at": None, "ended_at": None}},
    )
    users.update_many(
        {},
        {
            "$set": {
                "alive": True,
                "kicked_by": None,
                "discovered_opponent_ids": [],
            }
        },
    )
    await context.bot.send_message(tg_id, "Игра сброшена.")
    user = users.find_one({"telegram_id": tg_id})
    await send_menu(tg_id, user, get_game(), context)


def main() -> None:
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_handler(CallbackQueryHandler(code_button, pattern="^menu_code$"))
    application.add_handler(CallbackQueryHandler(list_button, pattern="^menu_list$"))
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    application.add_handler(CallbackQueryHandler(kick_action, pattern=r"^kick:"))
    application.add_handler(CallbackQueryHandler(confirm_kick, pattern="^confirm_kick$"))
    application.add_handler(CallbackQueryHandler(cancel_kick, pattern="^cancel_kick$"))
    application.add_handler(CallbackQueryHandler(start_game, pattern="^start_game$"))
    application.add_handler(CallbackQueryHandler(end_game, pattern="^end_game$"))
    application.add_handler(CallbackQueryHandler(reset_game, pattern="^reset_game$"))

    application.run_polling()


if __name__ == "__main__":
    main()
