import { en } from '../../i18n/en';
import { es } from '../../i18n/es';
import { zh } from '../../i18n/zh';
import { localizeStatus } from '../localizeStatus';

describe('localizeStatus', () => {
  it('localizes OCPP statuses in every supported language', () => {
    expect(localizeStatus('Offline', zh)).toBe('离线');
    expect(localizeStatus('Faulted', zh)).toBe('故障');
    expect(localizeStatus('Available', es)).toBe('Disponible');
    expect(localizeStatus('Charging', en)).toBe('Charging');
  });

  it('normalizes separators and does not leak unknown backend values', () => {
    expect(localizeStatus('Suspended_EVSE', zh)).toBe('已暂停');
    expect(localizeStatus('vendor_private_state', zh)).toBe('未知');
  });

  it('provides critical charging and QR errors in all three languages', () => {
    expect(zh.scan.invalidQrDetail).toContain('qr_token');
    expect(en.scan.invalidQrDetail).toContain('qr_token');
    expect(es.scan.invalidQrDetail).toContain('qr_token');
    expect(zh.charging.insufficientBalance).toBe('余额不足');
    expect(en.charging.insufficientBalance).toBe('Insufficient balance');
    expect(es.charging.insufficientBalance).toBe('Saldo insuficiente');
  });
});
