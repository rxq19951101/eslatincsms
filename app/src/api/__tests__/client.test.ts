import { parseApiErrorPayload } from '../client';

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

describe('API error envelope', () => {
  it('parses the canonical backend envelope and stable field paths', () => {
    expect(parseApiErrorPayload({
      success: false,
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Request validation failed',
        details: [
          { field: 'qr_token', path: ['body', 'qr_token'], message: 'String should have at least 10 characters', type: 'string_too_short' },
          { field: 'session_id', path: ['query', 'session_id'], message: 'Input should be a valid UUID', type: 'uuid_parsing' },
        ],
      },
    }, 422)).toEqual({
      message: 'Request validation failed',
      code: 'VALIDATION_ERROR',
      status: 422,
      details: [
        { field: 'qr_token', path: ['body', 'qr_token'], message: 'String should have at least 10 characters', type: 'string_too_short' },
        { field: 'session_id', path: ['query', 'session_id'], message: 'Input should be a valid UUID', type: 'uuid_parsing' },
      ],
      fieldErrors: {
        qr_token: 'String should have at least 10 characters',
        session_id: 'Input should be a valid UUID',
      },
    });
  });

  it('retains legacy FastAPI detail loc/msg compatibility', () => {
    const parsed = parseApiErrorPayload({
      detail: [{ loc: ['body', 'qr_token'], msg: 'Invalid QR token', type: 'value_error' }],
    }, 422);
    expect(parsed.message).toBe('Invalid QR token');
    expect(parsed.fieldErrors).toEqual({ qr_token: 'Invalid QR token' });
  });

  it('parses stable business errors from FastAPI detail objects', () => {
    const parsed = parseApiErrorPayload({
      detail: {
        code: 'TARIFF_NOT_CONFIGURED',
        message: 'This charger is not currently available for commercial charging.',
      },
    }, 409);
    expect(parsed.code).toBe('TARIFF_NOT_CONFIGURED');
    expect(parsed.message).toBe('This charger is not currently available for commercial charging.');
  });
});
