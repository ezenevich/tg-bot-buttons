import { Schema, model, Document } from 'mongoose';

export interface IGame extends Document {
  status: 'waiting' | 'running' | 'ended';
  adminIds: number[];
  startedAt?: Date;
  endedAt?: Date;
  createdAt: Date;
  updatedAt: Date;
}

const GameSchema = new Schema<IGame>({
  status: { type: String, enum: ['waiting', 'running', 'ended'], default: 'waiting' },
  adminIds: [Number],
  startedAt: Date,
  endedAt: Date
}, { timestamps: true });

export const Game = model<IGame>('Game', GameSchema);
