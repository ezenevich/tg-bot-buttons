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

awaiting_code: Set[int] = set()
pending_kick: Dict[int, str] = {}


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
    user = users.find_one({"telegram_id": tg_id})
    if not user:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        user = {
            "telegram_id": tg_id,
            "username": update.effective_user.username,
            "first_name": update.effective_user.first_name,
            "last_name": update.effective_user.last_name,
            "code": code,
            "alive": True,
            "discovered_opponent_ids": [],
        }
        users.insert_one(user)
    game = get_game()
    if not user.get("alive", True):
        kicker = users.find_one({"_id": user.get("kicked_by")})
        text = f"Game over. You were kicked by {get_name(kicker) if kicker else 'someone'}."
        await update.message.reply_text(text)
        return
    if game.get("status") != "running":
        await update.message.reply_text("Game has not started yet.")
        return
    await update.message.reply_text("Game on! Use /code to enter code or /list to see opponents.")


async def code_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    game = get_game()
    if game.get("status") != "running":
        await update.message.reply_text("Game hasn't started.")
        return
    user = users.find_one({"telegram_id": tg_id})
    if not user or not user.get("alive", True):
        await update.message.reply_text("Game over.")
        return
    awaiting_code.add(tg_id)
    await update.message.reply_text("Send a code to try.")


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
        await update.message.reply_text("That's your own code!")
        return
    opponent = users.find_one({"code": code, "alive": True})
    if not opponent:
        await update.message.reply_text("No match.")
        return
    if opponent["_id"] in user.get("discovered_opponent_ids", []):
        await update.message.reply_text("Already discovered.")
        return
    users.update_one(
        {"_id": user["_id"]},
        {"$addToSet": {"discovered_opponent_ids": opponent["_id"]}},
    )
    users.update_one(
        {"_id": opponent["_id"]},
        {"$addToSet": {"discovered_opponent_ids": user["_id"]}},
    )
    await update.message.reply_text(f"You discovered {get_name(opponent)}.")
    await context.bot.send_message(
        opponent["telegram_id"], f"You discovered {get_name(user)}."
    )


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    game = get_game()
    if game.get("status") != "running":
        await update.message.reply_text("Game hasn't started.")
        return
    user = users.find_one({"telegram_id": tg_id})
    if not user or not user.get("alive", True):
        await update.message.reply_text("Game over.")
        return
    ids = user.get("discovered_opponent_ids", [])
    opponents = list(users.find({"_id": {"$in": ids}, "alive": True}))
    if not opponents:
        await update.message.reply_text("No available opponents yet.")
        return
    buttons = [
        [InlineKeyboardButton(get_name(o), callback_data=f"kick:{o['_id']}")]
        for o in opponents
    ]
    await update.message.reply_text(
        "Available opponents:", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def kick_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    opponent_id = query.data.split(":", 1)[1]
    pending_kick[query.from_user.id] = opponent_id
    buttons = [
        [
            InlineKeyboardButton("Yes", callback_data="confirm_kick"),
            InlineKeyboardButton("No", callback_data="cancel_kick"),
        ]
    ]
    await query.message.reply_text(
        "Confirm kick?", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def confirm_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    opponent_id = pending_kick.get(tg_id)
    if not opponent_id:
        return
    pending_kick.pop(tg_id, None)
    user = users.find_one({"telegram_id": tg_id})
    opponent = users.find_one({"_id": ObjectId(opponent_id)})
    if not user or not opponent:
        await query.message.reply_text("Something went wrong.")
        return
    result = users.update_one(
        {"_id": opponent["_id"], "alive": True},
        {"$set": {"alive": False, "kicked_by": user["_id"]}},
    )
    if result.modified_count == 0:
        await query.message.reply_text("Opponent already out.")
        return
    await query.message.reply_text(f"You kicked {get_name(opponent)}.")
    await context.bot.send_message(
        opponent["telegram_id"],
        f"You were kicked by {get_name(user)}. Your game is over.",
    )


async def cancel_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    pending_kick.pop(query.from_user.id, None)
    await query.message.edit_text("Kick cancelled.")


async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    game = get_game()
    if not is_admin(game, tg_id):
        return
    if game.get("status") != "waiting":
        await update.message.reply_text("Game already started.")
        return
    games.update_one(
        {"_id": game["_id"]},
        {
            "$set": {"status": "running", "started_at": datetime.utcnow(), "ended_at": None}
        },
    )
    users.update_many({}, {"$set": {"discovered_opponent_ids": []}})
    await update.message.reply_text("Game started!")


async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    game = get_game()
    if not is_admin(game, tg_id):
        return
    if game.get("status") != "running":
        await update.message.reply_text("Game not running.")
        return
    games.update_one(
        {"_id": game["_id"]},
        {"$set": {"status": "ended", "ended_at": datetime.utcnow()}},
    )
    await update.message.reply_text("Game ended.")


async def reset_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
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
    await update.message.reply_text("Game reset.")


def main() -> None:
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("code", code_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("start_game", start_game))
    application.add_handler(CommandHandler("end_game", end_game))
    application.add_handler(CommandHandler("reset_game", reset_game))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_handler(CallbackQueryHandler(kick_action, pattern=r"^kick:"))
    application.add_handler(CallbackQueryHandler(confirm_kick, pattern="^confirm_kick$"))
    application.add_handler(CallbackQueryHandler(cancel_kick, pattern="^cancel_kick$"))

    application.run_polling()


if __name__ == "__main__":
    main()
