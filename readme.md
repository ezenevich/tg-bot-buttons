# Telegram Game Bot

Простой бот-игра для Telegram на Python с использованием [python-telegram-bot](https://python-telegram-bot.org/) и [MongoDB](https://www.mongodb.com/).

## Возможности
- `/start` — регистрация игрока и показ меню действий
- Ввод секретного кода и список противников через инлайн-кнопки
- Выбивание обнаруженных противников с подтверждением
- Кнопки администратора: старт игры, завершение и сброс

## Разработка

Создайте файл `.env` со следующими параметрами:

```
BOT_TOKEN=telegram-bot-token
MONGO_URI=mongodb://root:root@localhost:27017/tg-game?authSource=admin
ADMIN_IDS=123456789
```

Установите зависимости и запустите бота:

```
pip install -r requirements.txt
python bot.py
```

## Docker

Запустите бота и MongoDB через Docker Compose:

```
cp .env.example .env
docker compose up --build
```
