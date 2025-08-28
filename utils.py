from typing import Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from storage import games, ADMIN_IDS, START_KEYBOARD, SQUARE_NUMBERS, emoji_pairs


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


def number_to_circle(n) -> str:
    if isinstance(n, int):
        pair = emoji_pairs.find_one({"number": n})
        if pair:
            return pair.get("circle", "")
    return ""


async def send_menu(
    chat_id: int, user: Dict, game: Dict, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if game.get("status") != "running" and not is_admin(game, chat_id):
        await context.bot.send_message(chat_id, "Игра еще не началась.")
        return
    buttons = []
    if game.get("status") == "running" and not is_admin(game, chat_id):
        buttons.extend(
            [
                [InlineKeyboardButton("Ввести код", callback_data="menu_code")],
                [InlineKeyboardButton("Доступные кнопки", callback_data="menu_list")],
            ]
        )
    if is_admin(game, chat_id):
        if game.get("status") == "waiting":
            buttons.append(
                [
                    InlineKeyboardButton("Начать игру", callback_data="start_game"),
                    InlineKeyboardButton("Добавить коды", callback_data="add_codes"),
                ]
            )
            buttons.append(
                [InlineKeyboardButton("Игроки", callback_data="player_list")]
            )
            buttons.append(
                [InlineKeyboardButton("Пары", callback_data="show_pairs")]
            )
        elif game.get("status") == "running":
            buttons.append(
                [
                    InlineKeyboardButton("Завершить игру", callback_data="end_game"),
                    InlineKeyboardButton(
                        "Список игроков", callback_data="player_list"
                    ),
                ]
            )
            buttons.append(
                [InlineKeyboardButton("Кнопки", callback_data="button_status")]
            )
            buttons.append(
                [
                    InlineKeyboardButton(
                        "Добавить особую кнопку", callback_data="add_special"
                    )
                ]
            )
    if buttons:
        await context.bot.send_message(
            chat_id, "Выберите действие:", reply_markup=InlineKeyboardMarkup(buttons)
        )
