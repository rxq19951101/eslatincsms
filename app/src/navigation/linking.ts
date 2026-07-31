import type { LinkingOptions } from '@react-navigation/native';
import type { RootStackParamList } from '../types';

export const linking: LinkingOptions<RootStackParamList> = {
  prefixes: ['eslatin://'],
  config: {
    screens: {
      ResetPassword: {
        path: 'reset-password',
        parse: {
          token: (token) => token,
        },
      },
    },
  },
};
