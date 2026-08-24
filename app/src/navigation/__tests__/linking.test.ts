import { getStateFromPath } from '@react-navigation/native';

import appConfig from '../../../app.json';
import { linking } from '../linking';

describe('App password recovery deep linking', () => {
  it('keeps the eslatin native URL scheme in Expo config', () => {
    expect(appConfig.expo.scheme).toBe('eslatin');
    expect(linking.prefixes).toContain('eslatin://');
  });

  it('routes reset-password links to ResetPassword with the token', () => {
    const state = getStateFromPath(
      'reset-password?token=one-time-token',
      linking.config
    );

    expect(state?.routes).toEqual([
      {
        name: 'ResetPassword',
        path: 'reset-password?token=one-time-token',
        params: { token: 'one-time-token' },
      },
    ]);
  });

  it('routes payment returns using only the opaque checkout reference and safe status', () => {
    const state = linking.getStateFromPath?.(
      'payment-return?checkout_session_id=checkout-1&status=processing&token=ignored',
      linking.config,
    );

    expect(state?.routes).toEqual([
      {
        name: 'PaymentResult',
        path: 'payment-return',
        params: { checkout_session_id: 'checkout-1', status: 'processing' },
      },
    ]);
  });

  it('routes localhost web payment returns to the same result screen', () => {
    const state = linking.getStateFromPath?.(
      'payment-return?checkout_session_id=checkout-web-1&status=approved',
      linking.config,
    );

    expect(state?.routes).toEqual([
      {
        name: 'PaymentResult',
        path: 'payment-return',
        params: { checkout_session_id: 'checkout-web-1', status: 'approved' },
      },
    ]);
  });
});
