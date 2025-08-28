import os
from typing import Dict, Set

from dotenv import load_dotenv
from pymongo import MongoClient
from telegram import ReplyKeyboardMarkup, KeyboardButton

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
emoji_pairs = db["emoji_pairs"]

# Ensure each Telegram user ID is stored only once
users.create_index("telegram_id", unique=True)

awaiting_code: Set[int] = set()
pending_kick: Dict[int, str] = {}
awaiting_admin_codes: Set[int] = set()

CIRCLE_EMOJIS = ["🔴", "🟠", "🟡", "🟢", "🔵", "🟣", "🟤", "⚫", "⚪"]
SQUARE_NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]

if emoji_pairs.count_documents({}) == 0:
    for circle, square in zip(CIRCLE_EMOJIS, SQUARE_NUMBERS):
        emoji_pairs.insert_one({"circle": circle, "square": square})

# Reply keyboard with a physical "Начать" button so players can always return to the menu
START_KEYBOARD = ReplyKeyboardMarkup([[KeyboardButton("Начать")]], resize_keyboard=True)
