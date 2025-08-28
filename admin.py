import random
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from storage import (
    users,
    games,
    awaiting_admin_codes,
    ADMIN_IDS,
    START_KEYBOARD,
    emoji_pairs,
)
from utils import (
    get_game,
    is_admin,
    send_menu,
    get_name,
    number_to_square,
    number_to_circle,
)


async def add_codes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    tg_id = query.from_user.id
    game = get_game()
    if not is_admin(game, tg_id):
        return
    awaiting_admin_codes.add(tg_id)
    await context.bot.send_message(tg_id, "Отправьте коды через пробел.")


async def player_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    tg_id = query.from_user.id
    game = get_game()
    if not is_admin(game, tg_id):
        return
    players = list(users.find({"telegram_id": {"$nin": game.get("admin_ids", [])}}))
    players.sort(key=lambda p: p.get("number", 0))
    if players:
        text = "Подключенные игроки:\n" + "\n".join(
            f"{get_name(p)} {number_to_square(p.get('number'))}{number_to_circle(p.get('number'))} "
            f"{p.get('code') or '-'} "
            f"{'в игре ✅' if p.get('alive', True) else 'заблокирован 🚫'}"
            for p in players
        )
    else:
        text = "Нет подключенных игроков."
    await context.bot.send_message(tg_id, text)
    user = users.find_one({"telegram_id": tg_id})
    await send_menu(tg_id, user, game, context)


async def show_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    tg_id = query.from_user.id
    game = get_game()
    if not is_admin(game, tg_id):
        return
    pairs = list(emoji_pairs.find().sort("number", 1))
    text = "Пары:\n" + "\n".join(
        f"{number_to_square(p['number'])} - {p['circle']} "
        f"{'заблокирована' if p.get('blocked') else ('занята' if p.get('taken') else 'свободна')}"
        for p in pairs
    )
    buttons = [
        [InlineKeyboardButton("Перемешать пары", callback_data="shuffle_pairs")],
        [InlineKeyboardButton("Назад", callback_data="back_to_menu")],
    ]
    await context.bot.send_message(
        tg_id, text, reply_markup=InlineKeyboardMarkup(buttons)
    )


async def button_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    tg_id = query.from_user.id
    game = get_game()
    if not is_admin(game, tg_id):
        return
    pairs = list(emoji_pairs.find({"taken": True}).sort("number", 1))
    lines = []
    for p in pairs:
        number = number_to_square(p["number"])
        circle = p["circle"]
        player = users.find_one({"number": p["number"]})
        if not player:
            continue
        status = ["Есть игрок 👤"]
        if not player.get("alive", True) or p.get("blocked"):
            status.append("Заблокирована 🚫")
        elif player.get("code_used"):
            status.append("На руках ✋")
        else:
            status.append("В игре ⛳")
        lines.append(f"{number} {circle} - {', '.join(status)}")
    buttons = [[InlineKeyboardButton("Назад", callback_data="back_to_menu")]]
    await context.bot.send_message(
        tg_id, "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons)
    )


async def shuffle_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    tg_id = query.from_user.id
    game = get_game()
    if not is_admin(game, tg_id):
        return
    pairs = list(emoji_pairs.find().sort("number", 1))
    circles = [p["circle"] for p in pairs]
    random.shuffle(circles)
    emoji_pairs.delete_many({})
    for i, circle in enumerate(circles, start=1):
        emoji_pairs.insert_one(
            {"number": i, "circle": circle, "taken": False, "blocked": False}
        )
    pairs = list(emoji_pairs.find().sort("number", 1))
    text = "Пары перемешаны:\n" + "\n".join(
        f"{number_to_square(p['number'])} - {p['circle']}" for p in pairs
    )
    buttons = [
        [InlineKeyboardButton("Перемешать пары", callback_data="shuffle_pairs")],
        [InlineKeyboardButton("Назад", callback_data="back_to_menu")],
    ]
    await context.bot.send_message(
        tg_id, text, reply_markup=InlineKeyboardMarkup(buttons)
    )


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
    players = list(
        users.find({"telegram_id": {"$nin": game.get("admin_ids", [])}, "code": None})
    )
    codes = game.get("codes", [])
    if len(codes) < len(players):
        await context.bot.send_message(tg_id, "Недостаточно кодов для всех игроков.")
        user = users.find_one({"telegram_id": tg_id})
        await send_menu(tg_id, user, game, context)
        return
    random.shuffle(codes)
    assigned = codes[: len(players)]
    for player, code in zip(players, assigned):
        users.update_one({"_id": player["_id"]}, {"$set": {"code": code}})
    remaining = codes[len(players) :]
    games.update_one(
        {"_id": game["_id"]},
        {
            "$set": {
                "status": "running",
                "started_at": datetime.utcnow(),
                "ended_at": None,
                "codes": remaining,
            }
        },
    )
    users.update_many({}, {"$set": {"discovered_opponent_ids": [], "code_used": False}})
    for u in users.find({}):
        await context.bot.send_message(
            u["telegram_id"],
            "Игра началась! Нажмите \"Начать\", чтобы открыть меню.",
            reply_markup=START_KEYBOARD,
        )
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
    # Notify all connected players about game end before resetting
    players = list(
        users.find({"telegram_id": {"$nin": game.get("admin_ids", [])}})
    )
    for p in players:
        await context.bot.send_message(p["telegram_id"], "Игра завершена.")
    games.update_one(
        {"_id": game["_id"]},
        {
            "$set": {
                "status": "waiting",
                "started_at": None,
                "ended_at": None,
                "codes": [],
            }
        },
    )
    users.delete_many({"telegram_id": {"$nin": ADMIN_IDS}})
    users.update_many(
        {"telegram_id": {"$in": ADMIN_IDS}},
        {
            "$set": {
                "alive": True,
                "kicked_by": None,
                "discovered_opponent_ids": [],
                "code": None,
                "isAdmin": True,
                "code_used": False,
            }
        },
    )
    emoji_pairs.update_many({}, {"$set": {"taken": False, "blocked": False}})
    await context.bot.send_message(tg_id, "Игра завершена.")
    user = users.find_one({"telegram_id": tg_id})
    await send_menu(tg_id, user, get_game(), context)


def register_admin_handlers(application):
    application.add_handler(CallbackQueryHandler(start_game, pattern="^start_game$"))
    application.add_handler(CallbackQueryHandler(end_game, pattern="^end_game$"))
    application.add_handler(CallbackQueryHandler(add_codes, pattern="^add_codes$"))
    application.add_handler(CallbackQueryHandler(player_list, pattern="^player_list$"))
    application.add_handler(CallbackQueryHandler(show_pairs, pattern="^show_pairs$"))
    application.add_handler(CallbackQueryHandler(shuffle_pairs, pattern="^shuffle_pairs$"))
    application.add_handler(
        CallbackQueryHandler(button_status, pattern="^button_status$")
    )
