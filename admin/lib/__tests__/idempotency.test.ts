import { describe, expect, it, vi } from 'vitest';

import { IdempotencyIntentStore, requestIntent } from '@/lib/idempotency';

describe('idempotency intent lifecycle', () => {
  function createStore() {
    let sequence = 0;
    const createKey = vi.fn(() => `key-${++sequence}`);
    return { store: new IdempotencyIntentStore(createKey), createKey };
  }

  it('reuses the same key after a failed or timed-out retry', () => {
    const { store, createKey } = createStore();
    const intent = requestIntent('wallet-adjust:user-1', {
      amount: '10.25',
      description: 'Manual reconciliation',
    });

    const firstAttempt = store.keyFor(intent);
    const retryAfterFailure = store.keyFor(intent);

    expect(retryAfterFailure).toBe(firstAttempt);
    expect(createKey).toHaveBeenCalledTimes(1);
  });

  it('creates a new key only after success or a parameter change', () => {
    const { store, createKey } = createStore();
    const firstIntent = requestIntent('ocpp-remote-stop', {
      charge_point_id: 'CO.BOGOTA:CP-01',
      transaction_id: 731,
    });
    const changedIntent = requestIntent('ocpp-remote-stop', {
      charge_point_id: 'CO.BOGOTA:CP-01',
      transaction_id: 732,
    });

    expect(store.keyFor(firstIntent)).toBe('key-1');
    expect(store.keyFor(changedIntent)).toBe('key-2');
    expect(store.keyFor(firstIntent)).toBe('key-3');
    store.markSucceeded(firstIntent);
    expect(store.keyFor(firstIntent)).toBe('key-4');
    expect(createKey).toHaveBeenCalledTimes(4);
  });

  it('supports an explicit new intent with unchanged parameters', () => {
    const { store } = createStore();
    const intent = requestIntent('ocpp-reset', {
      charge_point_id: 'CO.BOGOTA:CP-01',
      type: 'Hard',
    });

    expect(store.keyFor(intent)).toBe('key-1');
    expect(store.startNew(intent)).toBe('key-2');
    expect(store.keyFor(intent)).toBe('key-2');
  });
});
