import { makeIdempotencyKey } from '@/lib/validation';

type KeyFactory = () => string;

export class IdempotencyIntentStore {
  private pending: { intent: string; key: string } | null = null;

  constructor(private readonly createKey: KeyFactory = makeIdempotencyKey) {}

  keyFor(intent: string): string {
    if (this.pending?.intent === intent) return this.pending.key;
    const created = this.createKey();
    this.pending = { intent, key: created };
    return created;
  }

  markSucceeded(intent: string): void {
    if (this.pending?.intent === intent) this.pending = null;
  }

  startNew(intent: string): string {
    const created = this.createKey();
    this.pending = { intent, key: created };
    return created;
  }

  clear(): void {
    this.pending = null;
  }
}

export function requestIntent(operation: string, payload: unknown): string {
  return `${operation}:${JSON.stringify(payload)}`;
}
