# Telegram Game Bot

Simple Telegram game bot written in Python using [python-telegram-bot](https://python-telegram-bot.org/) and [MongoDB](https://www.mongodb.com/).

## Features
- `/start` — register player and show status
- `/code` — submit secret codes to discover opponents
- `/list` — show discovered opponents
- `/kick` — eliminate a discovered opponent
- `/start_game`, `/end_game`, `/reset_game` — admin controls

## Development

Create a `.env` file with:

```
BOT_TOKEN=telegram-bot-token
MONGO_URI=mongodb://root:root@localhost:27017/tg-game?authSource=admin
ADMIN_IDS=123456789
```

Install dependencies and run:

```
pip install -r requirements.txt
python bot.py
```

## Docker

Run the bot and MongoDB with Docker Compose:

```
cp .env.example .env
docker compose up --build
```
