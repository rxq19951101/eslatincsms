import { parseQrPayload } from '../qrPayload';

describe('parseQrPayload', () => {
  it.each([
    ['qr:server-token-123', 'server-token-123'],
    ['{"qrToken":"camel-token"}', 'camel-token'],
    ['{"qr_token":"snake-token"}', 'snake-token'],
  ])('accepts the public scan payload %s', (payload, token) => {
    expect(parseQrPayload(payload)).toEqual({ qrToken: token });
  });

  it.each(['', 'raw-token', '{"charge_point_id":"internal-id"}', '["qr:token"]', '{invalid'])
    ('rejects unsupported or internal-id payload %s', (payload) => {
      expect(parseQrPayload(payload)).toBeNull();
    });
});
