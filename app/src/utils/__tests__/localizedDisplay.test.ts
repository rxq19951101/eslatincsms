import { en } from '../../i18n/en';
import { es } from '../../i18n/es';
import { zh } from '../../i18n/zh';
import {
  formatDateTime,
  localizeChargingFailure,
  localizeWalletTransaction,
  publicChargerIdentity,
} from '../localizedDisplay';
import type { WalletTransaction } from '../../types';

const internalUuid = '22222222-2222-4222-8222-222222222222';
const transaction: WalletTransaction = {
  id: internalUuid,
  type: 'charge',
  reference: `charge_${internalUuid}`,
  description: '充电结算（后端旧文案）',
  amount: -1200,
  created_at: '2026-07-18T12:00:00Z',
  charge_point_name: 'Centro Norte',
};

describe('localized user-visible values', () => {
  it.each([
    [zh, '充电扣费 · Centro Norte'],
    [en, 'Charging charge · Centro Norte'],
    [es, 'Cargo por carga · Centro Norte'],
  ])('builds wallet labels from structured fields and hides internal references', (t, expected) => {
    const label = localizeWalletTransaction(transaction, t);
    expect(label).toBe(expected);
    expect(label).not.toContain(internalUuid);
    expect(label).not.toContain(transaction.description as string);
  });

  it('uses only the public OCPP identity as a charger label', () => {
    expect(publicChargerIdentity({ ocpp_identity: 'CP-PUBLIC-001' })).toBe('CP-PUBLIC-001');
    expect(publicChargerIdentity({})).toBe('—');
  });

  it('formats timestamps using the selected App locale', () => {
    const spy = jest.spyOn(Date.prototype, 'toLocaleString').mockReturnValue('localized');
    expect(formatDateTime('2026-07-18T12:00:00Z', 'zh')).toBe('localized');
    expect(spy).toHaveBeenCalledWith('zh-CN', expect.any(Object));
    spy.mockRestore();
  });

  it('localizes stable backend error semantics after a language switch', () => {
    const failure = { operation: 'start' as const, code: 'REMOTE_START_TIMEOUT', status: 504 };
    expect(localizeChargingFailure(failure, zh)).toBe(zh.charging.startTimeout);
    expect(localizeChargingFailure(failure, en)).toBe(en.charging.startTimeout);
    expect(localizeChargingFailure(failure, es)).toBe(es.charging.startTimeout);
  });
});
