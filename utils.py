from typing import Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from storage import games, ADMIN_IDS, START_KEYBOARD


def get_name(user: Dict) -> str:
    return "@" + (user.get("username") or user.get("first_name") or "user")


def get_game() -> Dict:
    game = games.find_one()
    if not game:
        game = {"status": "waiting", "admin_ids": ADMIN_IDS, "codes": []}
        games.insert_one(game)
    return game


def is_admin(game: Dict, tg_id: int) -> bool:
    return tg_id in game.get("admin_ids", [])


async def send_menu(
    chat_id: int, user: Dict, game: Dict, context: ContextTypes.DEFAULT_TYPE
) -> None:
    await context.bot.send_message(
        chat_id,
        "Для возвращения в меню используйте кнопку \"Начать\"",
        reply_markup=START_KEYBOARD,
    )
    if game.get("status") != "running" and not is_admin(game, chat_id):
        await context.bot.send_message(chat_id, "Игра еще не началась.")
        return
    buttons = []
    if game.get("status") == "running" and not is_admin(game, chat_id):
        buttons.extend(
            [
                [InlineKeyboardButton("Ввести код", callback_data="menu_code")],
                [InlineKeyboardButton("Список противников", callback_data="menu_list")],
            ]
        )
    if is_admin(game, chat_id):
        admin_buttons = []
        if game.get("status") == "waiting":
            admin_buttons.append(
                InlineKeyboardButton("Начать игру", callback_data="start_game")
            )
            admin_buttons.append(
                InlineKeyboardButton("Добавить коды", callback_data="add_codes")
            )
        elif game.get("status") == "running":
            admin_buttons.append(
                InlineKeyboardButton("Закончить игру", callback_data="end_game")
            )
            admin_buttons.append(
                InlineKeyboardButton("Сбросить игру", callback_data="reset_game")
            )
            admin_buttons.append(
                InlineKeyboardButton("Добавить коды", callback_data="add_codes")
            )
        else:
            admin_buttons.append(
                InlineKeyboardButton("Сбросить игру", callback_data="reset_game")
            )
        admin_buttons.append(
            InlineKeyboardButton("Игроки", callback_data="player_list")
        )
        if admin_buttons:
            buttons.append(admin_buttons)
    if buttons:
        await context.bot.send_message(
            chat_id, "Выберите действие:", reply_markup=InlineKeyboardMarkup(buttons)
        )
