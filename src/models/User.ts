import { Schema, model, Document, Types } from 'mongoose';

export interface IUser extends Document {
  telegramId: number;
  username?: string;
  firstName?: string;
  lastName?: string;
  code: string;
  alive: boolean;
  discoveredOpponentIds: Types.ObjectId[];
  kickedBy?: Types.ObjectId;
  createdAt: Date;
  updatedAt: Date;
}

const UserSchema = new Schema<IUser>({
  telegramId: { type: Number, unique: true },
  username: String,
  firstName: String,
  lastName: String,
  code: { type: String, index: true },
  alive: { type: Boolean, default: true },
  discoveredOpponentIds: [{ type: Schema.Types.ObjectId, ref: 'User' }],
  kickedBy: { type: Schema.Types.ObjectId, ref: 'User' }
}, { timestamps: true });

UserSchema.index({ telegramId: 1 }, { unique: true });
UserSchema.index({ code: 1, alive: 1 });

export const User = model<IUser>('User', UserSchema);
