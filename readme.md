# Telegram Game Bot

Simple Telegram game bot using [Telegraf](https://telegraf.js.org/) and [Mongoose](https://mongoosejs.com/).

## Features
- `/start` — register player and show status
- `/code` — submit secret codes to discover opponents
- `/list` — show discovered opponents
- `/kick` — eliminate a discovered opponent
- `/start_game`, `/end_game`, `/reset_game` — admin controls

## Development

Set environment variables:
```
BOT_TOKEN=telegram-bot-token
MONGO_URI=mongodb://localhost:27017/tg-game
```

Install dependencies and run:
```
npm install
npm run dev
```

Build and run:
```
npm run build
npm start
```

## Docker

Run the bot and MongoDB with Docker Compose:
```
cp .env.example .env
docker-compose up --build
```

