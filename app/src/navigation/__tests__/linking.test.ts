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
});
