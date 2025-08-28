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

from storage import (
    BOT_TOKEN,
    users,
    games,
    awaiting_code,
    awaiting_admin_codes,
    START_KEYBOARD,
    emoji_pairs,
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
                "code": None,
                "alive": True,
                "discovered_opponent_ids": [],
                "isAdmin": is_admin_flag,
                "number": number,
            }
        )
        user = users.find_one({"telegram_id": tg_id})
        if not is_admin_flag:
            square = number_to_square(number)
            circle = number_to_circle(number)
            emoji_pairs.update_one(
                {"number": number}, {"$set": {"taken": True, "blocked": False}}
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
    if tg_id not in awaiting_code:
        return
    awaiting_code.remove(tg_id)
    code = text.upper()
    user = users.find_one({"telegram_id": tg_id})
    if not user:
        return
    opponent = users.find_one(
        {"code": code, "alive": True, "code_used": {"$ne": True}}
    )
    if not opponent:
        blocked_user = users.find_one({"code": code, "alive": False})
        if blocked_user:
            await update.message.reply_text("Кнопка заблокирована.")
        else:
            await update.message.reply_text("Код не найден или уже использован.")
        await send_menu(tg_id, user, get_game(), context)
        return
    if opponent["_id"] in user.get("discovered_opponent_ids", []):
        await update.message.reply_text("Уже найден.")
        await send_menu(tg_id, user, get_game(), context)
        return
    result = users.update_one(
        {"_id": opponent["_id"], "code_used": {"$ne": True}},
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
    if not opponents:
        await context.bot.send_message(tg_id, "Нет доступных кнопок.")
        await send_menu(tg_id, user, game, context)
        return
    buttons = [
        [
            InlineKeyboardButton(
                number_to_circle(o.get("number")),
                callback_data=f"confirm_kick:{o['_id']}",
            )
        ]
        for o in opponents
    ]
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_menu")])
    await context.bot.send_message(
        tg_id, "Доступные кнопки:", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def confirm_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    opponent_id = query.data.split(":", 1)[1]
    opponent = users.find_one({"_id": ObjectId(opponent_id)})
    if not opponent:
        return
    square = number_to_square(opponent.get("number"))
    buttons = [
        [
            InlineKeyboardButton("Да", callback_data=f"kick:{opponent_id}"),
            InlineKeyboardButton("Нет", callback_data="cancel_kick"),
        ]
    ]
    await context.bot.send_message(
        query.from_user.id,
        f"Заблокировать игрока {square}?",
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
    emoji_pairs.update_one(
        {"number": opponent.get("number")}, {"$set": {"blocked": True}}
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
    application.add_handler(CallbackQueryHandler(kick_action, pattern=r"^kick:"))

    register_admin_handlers(application)

    application.run_polling()


if __name__ == "__main__":
    main()
