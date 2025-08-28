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

# Ensure each Telegram user ID is stored only once
users.create_index("telegram_id", unique=True)

awaiting_code: Set[int] = set()
pending_kick: Dict[int, str] = {}
awaiting_admin_codes: Set[int] = set()

# Reply keyboard with a physical "Начать" button so players can always return to the menu
START_KEYBOARD = ReplyKeyboardMarkup([[KeyboardButton("Начать")]], resize_keyboard=True)
