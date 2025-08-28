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
import random
from pymongo.errors import DuplicateKeyError

from storage import (
    BOT_TOKEN,
    users,
    games,
    awaiting_code,
    awaiting_admin_codes,
    awaiting_special_codes,
    START_KEYBOARD,
    buttons,
)
from utils import (
    get_name,
    get_game,
    is_admin,
    send_menu,
    number_to_square,
    number_to_circle,
)
from admin import register_admin_handlers


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    game = get_game()
    user = users.find_one({"telegram_id": tg_id})
    if not user:
        if game.get("status") == "running" and not is_admin(game, tg_id):
            await update.message.reply_text(
                "Игра уже идет, присоединиться нельзя.",
                reply_markup=START_KEYBOARD,
            )
            return
        is_admin_flag = is_admin(game, tg_id)
        number = None
        if not is_admin_flag:
            player_count = users.count_documents({"isAdmin": {"$ne": True}})
            if player_count >= 9:
                await update.message.reply_text(
                    "Нужное количество игроков уже в игре.",
                    reply_markup=START_KEYBOARD,
                )
                return
            number = player_count + 1
        users.insert_one(
            {
                "telegram_id": tg_id,
                "username": update.effective_user.username,
                "first_name": update.effective_user.first_name,
                "last_name": update.effective_user.last_name,
                "alive": True,
                "discovered_opponent_ids": [],
                "special_button_ids": [],
                "isAdmin": is_admin_flag,
                "number": number,
            }
        )
        user = users.find_one({"telegram_id": tg_id})
        if not is_admin_flag:
            square = number_to_square(number)
            circle = number_to_circle(number)
            buttons.update_one(
                {"number": number, "special": False},
                {
                    "$set": {
                        "taken": True,
                        "blocked": False,
                        "player_id": user["_id"],
                        "code_used": False,
                    }
                },
            )
            for admin_id in game.get("admin_ids", []):
                await context.bot.send_message(
                    admin_id,
                    f"Подключился игрок {get_name(user)} {square}{circle}",
                )
    if not user.get("alive", True):
        await update.message.reply_text(
            "Вас заблокировали 🚫. Игра окончена.", reply_markup=START_KEYBOARD
        )
        return
    if game.get("status") != "running":
        if is_admin(game, tg_id):
            await send_menu(tg_id, user, game, context)
        else:
            await update.message.reply_text(
                "Игра еще не началась.", reply_markup=START_KEYBOARD
            )
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
        await context.bot.send_message(
            tg_id, "Игра еще не началась.", reply_markup=START_KEYBOARD
        )
        if user and is_admin(game, tg_id):
            await send_menu(tg_id, user, game, context)
        return
    if not user or not user.get("alive", True):
        await context.bot.send_message(
            tg_id, "Вас заблокировали 🚫. Игра окончена.", reply_markup=START_KEYBOARD
        )
        return
    awaiting_code.add(tg_id)
    await context.bot.send_message(tg_id, "Отправьте код.")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    text = update.message.text.strip()
    if text.lower() == "начать":
        await start(update, context)
        return
    if tg_id in awaiting_admin_codes:
        game = get_game()
        codes = [c.strip().upper() for c in text.split() if c.strip()]
        if codes:
            games.update_one(
                {"_id": game["_id"]}, {"$addToSet": {"codes": {"$each": codes}}}
            )
            await update.message.reply_text("Коды добавлены.")
        else:
            await update.message.reply_text("Нет кодов.")
        awaiting_admin_codes.remove(tg_id)
        user = users.find_one({"telegram_id": tg_id})
        await send_menu(tg_id, user, game, context)
        return
    if tg_id in awaiting_special_codes:
        game = get_game()
        code = text.strip().upper()
        if code:
            try:
                buttons.insert_one(
                    {
                        "code": code,
                        "emoji": "\U0001F500",
                        "taken": False,
                        "blocked": False,
                        "code_used": False,
                        "special": True,
                    }
                )
                await update.message.reply_text("Особая кнопка добавлена.")
            except DuplicateKeyError:
                await update.message.reply_text("Такой код уже существует.")
        else:
            await update.message.reply_text("Нет кода.")
        awaiting_special_codes.remove(tg_id)
        user = users.find_one({"telegram_id": tg_id})
        await send_menu(tg_id, user, game, context)
        return
    if tg_id not in awaiting_code:
        return
    awaiting_code.remove(tg_id)
    code = text.upper()
    user = users.find_one({"telegram_id": tg_id})
    if not user:
        return
    btn = buttons.find_one(
        {
            "code": code,
            "special": False,
            "blocked": {"$ne": True},
            "code_used": {"$ne": True},
        }
    )
    if not btn:
        special = buttons.find_one(
            {
                "code": code,
                "special": True,
                "blocked": {"$ne": True},
                "taken": {"$ne": True},
            }
        )
        if special:
            buttons.update_one({"_id": special["_id"]}, {"$set": {"taken": True}})
            users.update_one(
                {"_id": user["_id"]},
                {"$addToSet": {"special_button_ids": special["_id"]}},
            )
            await update.message.reply_text(
                "Вы нашли особую кнопку. Она добавлена в доступные кнопки."
            )
        else:
            blocked_regular = buttons.find_one(
                {"code": code, "special": False, "blocked": True}
            )
            if blocked_regular:
                await update.message.reply_text("Кнопка заблокирована.")
            else:
                blocked_special = buttons.find_one(
                    {"code": code, "special": True, "blocked": True}
                )
                if blocked_special or buttons.find_one(
                    {"code": code, "special": True, "taken": True}
                ):
                    await update.message.reply_text("Код не найден или уже использован.")
                else:
                    await update.message.reply_text("Код не найден или уже использован.")
        await send_menu(tg_id, user, get_game(), context)
        return
    opponent = users.find_one({"_id": btn.get("player_id"), "alive": True})
    if not opponent:
        await update.message.reply_text("Код не найден или уже использован.")
        await send_menu(tg_id, user, get_game(), context)
        return
    if opponent["_id"] in user.get("discovered_opponent_ids", []):
        await update.message.reply_text("Уже найден.")
        await send_menu(tg_id, user, get_game(), context)
        return
    result = buttons.update_one(
        {"_id": btn["_id"], "code_used": {"$ne": True}},
        {"$set": {"code_used": True}},
    )
    if result.modified_count == 0:
        await update.message.reply_text("Код не найден или уже использован.")
        await send_menu(tg_id, user, get_game(), context)
        return
    users.update_one(
        {"_id": user["_id"]},
        {"$addToSet": {"discovered_opponent_ids": opponent["_id"]}},
    )
    await update.message.reply_text(
        f"Вы обнаружили {number_to_circle(opponent.get('number'))} кнопку."
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
        await context.bot.send_message(
            tg_id, "Игра еще не началась.", reply_markup=START_KEYBOARD
        )
        if user and is_admin(game, tg_id):
            await send_menu(tg_id, user, game, context)
        return
    if not user or not user.get("alive", True):
        await context.bot.send_message(
            tg_id, "Вас заблокировали 🚫. Игра окончена.", reply_markup=START_KEYBOARD
        )
        return
    ids = user.get("discovered_opponent_ids", [])
    opponents = list(users.find({"_id": {"$in": ids}, "alive": True}))
    special_ids = user.get("special_button_ids", [])
    specials = list(buttons.find({"_id": {"$in": special_ids}}))
    if not opponents and not specials:
        await context.bot.send_message(tg_id, "Нет доступных кнопок.")
        await send_menu(tg_id, user, game, context)
        return
    keyboard = []
    for o in opponents:
        keyboard.append(
            [
                InlineKeyboardButton(
                    number_to_circle(o.get("number")),
                    callback_data=f"confirm_kick:{o['_id']}",
                )
            ]
        )
    for s in specials:
        keyboard.append(
            [
                InlineKeyboardButton(
                    s.get("emoji", "\U0001F500"),
                    callback_data=f"use_special:{s['_id']}",
                )
            ]
        )
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_menu")])
    await context.bot.send_message(
        tg_id, "Доступные кнопки:", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def confirm_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    opponent_id = query.data.split(":", 1)[1]
    opponent = users.find_one({"_id": ObjectId(opponent_id)})
    if not opponent:
        return
    circle = number_to_circle(opponent.get("number"))
    buttons = [
        [
            InlineKeyboardButton("Да", callback_data=f"kick:{opponent_id}"),
            InlineKeyboardButton("Нет", callback_data="cancel_kick"),
        ]
    ]
    await context.bot.send_message(
        query.from_user.id,
        f"Нажать {circle} кнопку?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cancel_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    tg_id = query.from_user.id
    user = users.find_one({"telegram_id": tg_id})
    game = get_game()
    if user:
        await send_menu(tg_id, user, game, context)


async def use_special(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    btn_id = query.data.split(":", 1)[1]
    special = buttons.find_one({"_id": ObjectId(btn_id), "special": True})
    if not special:
        return
    tg_id = query.from_user.id
    user = users.find_one({"telegram_id": tg_id})
    if not user:
        return
    active = list(
        buttons.find(
            {
                "special": False,
                "player_id": {"$ne": None},
                "blocked": {"$ne": True},
            }
        )
    )
    triples = [(b["number"], b["circle"], b["player_id"]) for b in active]
    random.shuffle(triples)
    for b, (n, c, pid) in zip(active, triples):
        buttons.update_one(
            {"_id": b["_id"]},
            {"$set": {"number": n, "circle": c, "player_id": pid}},
        )
    buttons.update_one(
        {"_id": special["_id"]},
        {"$set": {"code_used": True, "blocked": True, "taken": True}},
    )
    users.update_one(
        {"_id": user["_id"]}, {"$pull": {"special_button_ids": special["_id"]}}
    )
    await context.bot.send_message(tg_id, "Кнопки изменили свой цвет!")
    await send_menu(tg_id, user, get_game(), context)


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
    tg_id = query.from_user.id
    opponent_id = query.data.split(":", 1)[1]
    user = users.find_one({"telegram_id": tg_id})
    opponent = users.find_one({"_id": ObjectId(opponent_id)})
    if not user or not opponent:
        return
    result = users.update_one(
        {"_id": opponent["_id"], "alive": True},
        {"$set": {"alive": False, "kicked_by": user["_id"]}},
    )
    if result.modified_count == 0:
        if opponent["telegram_id"] != tg_id:
            await send_menu(tg_id, user, get_game(), context)
        return
    buttons.update_one(
        {"player_id": opponent["_id"], "special": False},
        {"$set": {"blocked": True}},
    )
    await context.bot.send_message(
        opponent["telegram_id"], "Вас заблокировали 🚫. Игра окончена."
    )
    square = number_to_square(opponent.get("number"))
    message = f"Игрок {square} покидает игру."
    recipients = users.find(
        {"telegram_id": {"$ne": opponent["telegram_id"]}, "alive": True}
    )
    for r in recipients:
        await context.bot.send_message(r["telegram_id"], message)
    if opponent["_id"] == user["_id"]:
        available_ids = [
            oid for oid in user.get("discovered_opponent_ids", []) if oid != user["_id"]
        ]
        alive_players = list(
            users.find(
                {
                    "alive": True,
                    "telegram_id": {"$ne": tg_id},
                    "isAdmin": {"$ne": True},
                }
            )
        )
        if available_ids and alive_players:
            random.shuffle(alive_players)
            for i, btn_id in enumerate(available_ids):
                recipient = alive_players[i % len(alive_players)]
                users.update_one(
                    {"_id": recipient["_id"]},
                    {"$addToSet": {"discovered_opponent_ids": btn_id}},
                )
                btn_player = users.find_one({"_id": btn_id})
                if btn_player:
                    circle = number_to_circle(btn_player.get("number"))
                    await context.bot.send_message(
                        recipient["telegram_id"],
                        f"Вам досталась кнопка {circle} от {user.get('number')} игрока.",
                    )
    else:
        opponent_buttons = [
            oid for oid in opponent.get("discovered_opponent_ids", []) if oid != opponent["_id"]
        ]
        if opponent_buttons:
            for btn_id in opponent_buttons:
                users.update_one(
                    {"_id": user["_id"]},
                    {"$addToSet": {"discovered_opponent_ids": btn_id}},
                )
                btn_player = users.find_one({"_id": btn_id})
                if btn_player:
                    circle = number_to_circle(btn_player.get("number"))
                    await context.bot.send_message(
                        tg_id,
                        f"Вам досталась кнопка {circle} от {opponent.get('number')} игрока.",
                    )
        if opponent["telegram_id"] != tg_id:
            await send_menu(tg_id, user, get_game(), context)




def main() -> None:
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_handler(CallbackQueryHandler(code_button, pattern="^menu_code$"))
    application.add_handler(CallbackQueryHandler(list_button, pattern="^menu_list$"))
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    application.add_handler(CallbackQueryHandler(confirm_kick, pattern=r"^confirm_kick:"))
    application.add_handler(CallbackQueryHandler(cancel_kick, pattern="^cancel_kick$"))
    application.add_handler(CallbackQueryHandler(use_special, pattern=r"^use_special:"))
    application.add_handler(CallbackQueryHandler(kick_action, pattern=r"^kick:"))

    register_admin_handlers(application)

    application.run_polling()


if __name__ == "__main__":
    main()
