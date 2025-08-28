import random
from datetime import datetime

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from storage import users, games, awaiting_admin_codes, ADMIN_IDS, START_KEYBOARD
from utils import get_game, is_admin, send_menu, get_name


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
    if players:
        text = "Подключенные игроки:\n" + "\n".join(get_name(p) for p in players)
    else:
        text = "Нет подключенных игроков."
    await context.bot.send_message(tg_id, text)
    user = users.find_one({"telegram_id": tg_id})
    await send_menu(tg_id, user, game, context)


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
    users.update_many({}, {"$set": {"discovered_opponent_ids": []}})
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
            }
        },
    )
    await context.bot.send_message(tg_id, "Игра сброшена.")
    user = users.find_one({"telegram_id": tg_id})
    await send_menu(tg_id, user, get_game(), context)


def register_admin_handlers(application):
    application.add_handler(CallbackQueryHandler(start_game, pattern="^start_game$"))
    application.add_handler(CallbackQueryHandler(end_game, pattern="^end_game$"))
    application.add_handler(CallbackQueryHandler(reset_game, pattern="^reset_game$"))
    application.add_handler(CallbackQueryHandler(add_codes, pattern="^add_codes$"))
    application.add_handler(CallbackQueryHandler(player_list, pattern="^player_list$"))
