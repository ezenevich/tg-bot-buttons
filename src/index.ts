import { Telegraf, Markup } from 'telegraf';
import mongoose, { Types } from 'mongoose';
import { config } from 'dotenv';
import { User, IUser } from './models/User';
import { Game, IGame } from './models/Game';

config();

const botToken = process.env.BOT_TOKEN || '';
const mongoUri = process.env.MONGO_URI || '';

if (!botToken) {
  throw new Error('BOT_TOKEN not provided');
}

mongoose.connect(mongoUri).then(() => console.log('Mongo connected'));

const bot = new Telegraf(botToken);

async function getGame(): Promise<IGame> {
  let game = await Game.findOne();
  if (!game) {
    game = await Game.create({ status: 'waiting', adminIds: [] });
  }
  return game;
}

function getName(u: IUser): string {
  return `@${u.username || u.firstName || 'user'}`;
}

const awaitingCode = new Set<number>();
const pendingKick = new Map<number, string>();

bot.start(async ctx => {
  const tgId = ctx.from?.id;
  if (!tgId) return;
  let user = await User.findOne({ telegramId: tgId });
  if (!user) {
    user = await User.create({
      telegramId: tgId,
      username: ctx.from?.username,
      firstName: ctx.from?.first_name,
      lastName: ctx.from?.last_name,
      code: Math.random().toString(36).slice(-4).toUpperCase(),
      alive: true,
      discoveredOpponentIds: []
    });
  }
  const game = await getGame();
  if (!user.alive) {
    const kicker = user.kickedBy ? await User.findById(user.kickedBy) : null;
    await ctx.reply(`Game over. You were kicked by ${kicker ? getName(kicker) : 'someone'}.`);
    return;
  }
  if (game.status !== 'running') {
    await ctx.reply('Game has not started yet.');
    return;
  }
  await ctx.reply('Game on! Use /code to enter code or /list to see opponents.');
});

bot.command('code', async ctx => {
  const game = await getGame();
  if (game.status !== 'running') return ctx.reply('Game hasn\'t started.');
  const user = await User.findOne({ telegramId: ctx.from?.id });
  if (!user || !user.alive) return ctx.reply('Game over.');
  awaitingCode.add(ctx.from!.id);
  return ctx.reply('Send a code to try.');
});

bot.on('text', async ctx => {
  const tgId = ctx.from?.id;
  if (!tgId || !awaitingCode.has(tgId)) return;
  awaitingCode.delete(tgId);
  const code = ctx.message.text.trim();
  const user = await User.findOne({ telegramId: tgId });
  if (!user) return;
  if (code === user.code) {
    return ctx.reply('That\'s your own code!');
  }
  const opponent = await User.findOne({ code, alive: true });
  if (!opponent) {
    return ctx.reply('No match.');
  }
  if (user.discoveredOpponentIds.find(id => id.equals(opponent._id))) {
    return ctx.reply('Already discovered.');
  }
  user.discoveredOpponentIds.push(opponent._id);
  opponent.discoveredOpponentIds.push(user._id);
  await user.save();
  await opponent.save();
  await ctx.reply(`You discovered ${getName(opponent)}.`);
  await bot.telegram.sendMessage(opponent.telegramId, `You discovered ${getName(user)}.`);
});

bot.command('list', async ctx => {
  const game = await getGame();
  if (game.status !== 'running') return ctx.reply('Game hasn\'t started.');
  const user = await User.findOne({ telegramId: ctx.from?.id });
  if (!user || !user.alive) return ctx.reply('Game over.');
  const opponents = await User.find({ _id: { $in: user.discoveredOpponentIds }, alive: true });
  if (!opponents.length) return ctx.reply('No available opponents yet.');
  const buttons = opponents.map(o => [Markup.button.callback(getName(o), `kick:${o._id}`)]);
  return ctx.reply('Available opponents:', Markup.inlineKeyboard(buttons));
});

bot.action(/kick:(.+)/, async ctx => {
  const opponentId = ctx.match[1];
  pendingKick.set(ctx.from!.id, opponentId);
  await ctx.reply('Confirm kick?', Markup.inlineKeyboard([
    [Markup.button.callback('Yes', 'confirm_kick'), Markup.button.callback('No', 'cancel_kick')]
  ]));
});

bot.action('confirm_kick', async ctx => {
  const opponentId = pendingKick.get(ctx.from!.id);
  if (!opponentId) return ctx.answerCbQuery();
  pendingKick.delete(ctx.from!.id);
  const user = await User.findOne({ telegramId: ctx.from!.id });
  const opponent = await User.findById(opponentId);
  if (!user || !opponent) return ctx.reply('Something went wrong.');
  const result = await User.updateOne({ _id: opponentId, alive: true }, { alive: false, kickedBy: user._id });
  if (result.modifiedCount === 0) {
    return ctx.reply('Opponent already out.');
  }
  await ctx.reply(`You kicked ${getName(opponent)}.`);
  await bot.telegram.sendMessage(opponent.telegramId, `You were kicked by ${getName(user)}. Your game is over.`);
});

bot.action('cancel_kick', ctx => {
  pendingKick.delete(ctx.from!.id);
  ctx.editMessageText('Kick cancelled.');
});

function isAdmin(game: IGame, tgId: number | undefined): boolean {
  return !!tgId && game.adminIds.includes(tgId);
}

bot.command('start_game', async ctx => {
  const game = await getGame();
  if (!isAdmin(game, ctx.from?.id)) return;
  if (game.status !== 'waiting') return ctx.reply('Game already started.');
  game.status = 'running';
  game.startedAt = new Date();
  await game.save();
  await User.updateMany({}, { discoveredOpponentIds: [] });
  await ctx.reply('Game started!');
});

bot.command('end_game', async ctx => {
  const game = await getGame();
  if (!isAdmin(game, ctx.from?.id)) return;
  if (game.status !== 'running') return ctx.reply('Game not running.');
  game.status = 'ended';
  game.endedAt = new Date();
  await game.save();
  await ctx.reply('Game ended.');
});

bot.command('reset_game', async ctx => {
  const game = await getGame();
  if (!isAdmin(game, ctx.from?.id)) return;
  game.status = 'waiting';
  await game.save();
  await User.updateMany({}, { alive: true, kickedBy: null, discoveredOpponentIds: [] });
  await ctx.reply('Game reset.');
});

bot.launch();

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
