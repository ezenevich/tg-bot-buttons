from typing import Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from storage import games, ADMIN_IDS, START_KEYBOARD, SQUARE_NUMBERS


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


def number_to_square(n) -> str:
    if isinstance(n, int) and 1 <= n <= len(SQUARE_NUMBERS):
        return SQUARE_NUMBERS[n - 1]
    return ""


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
                InlineKeyboardButton("Завершить игру", callback_data="end_game")
            )
            admin_buttons.append(
                InlineKeyboardButton("Добавить коды", callback_data="add_codes")
            )
        admin_buttons.append(
            InlineKeyboardButton("Игроки", callback_data="player_list")
        )
        if admin_buttons:
            buttons.append(admin_buttons)
        buttons.append(
            [
                InlineKeyboardButton("Пары", callback_data="show_pairs"),
                InlineKeyboardButton("Перемешать пары", callback_data="shuffle_pairs"),
            ]
        )
    if buttons:
        await context.bot.send_message(
            chat_id, "Выберите действие:", reply_markup=InlineKeyboardMarkup(buttons)
        )
