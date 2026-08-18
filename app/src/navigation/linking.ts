import { getStateFromPath as getNavigationStateFromPath } from '@react-navigation/native';
import type { LinkingOptions } from '@react-navigation/native';
import type { PaymentReturnStatus, RootStackParamList } from '../types';

const MAX_CHECKOUT_SESSION_ID_LENGTH = 256;

export const parseCheckoutSessionId = (value: string): string | undefined => {
  const normalized = value.trim();
  return normalized && normalized.length <= MAX_CHECKOUT_SESSION_ID_LENGTH
    ? normalized
    : undefined;
};

export const parsePaymentReturnStatus = (value: string): PaymentReturnStatus | undefined => {
  if (
    value === 'created' ||
    value === 'ready' ||
    value === 'processing' ||
    value === 'action_required' ||
    value === 'approved' ||
    value === 'declined' ||
    value === 'expired' ||
    value === 'error'
  ) {
    return value;
  }
  return undefined;
};

const sanitizePaymentReturnState = (state: unknown): any => {
  if (!state) return state;
  const navigationState = state as {
    routes: Array<{ name: string; params?: Record<string, unknown>; path?: string }>;
    [key: string]: unknown;
  };
  return {
    ...navigationState,
    routes: navigationState.routes.map((route) => {
      if (route.name !== 'PaymentResult') return route;
      const params = route.params as Record<string, unknown> | undefined;
      const checkoutSessionId = typeof params?.checkout_session_id === 'string'
        ? parseCheckoutSessionId(params.checkout_session_id)
        : undefined;
      const status = typeof params?.status === 'string'
        ? parsePaymentReturnStatus(params.status)
        : undefined;
      return {
        ...route,
        path: 'payment-return',
        params: {
          ...(checkoutSessionId ? { checkout_session_id: checkoutSessionId } : {}),
          ...(status ? { status } : {}),
        },
      };
    }),
  };
};

export const linking: LinkingOptions<RootStackParamList> = {
  prefixes: ['eslatin://', 'http://localhost:8081'],
  getStateFromPath: (path, options) =>
    sanitizePaymentReturnState(getNavigationStateFromPath(path, options)),
  config: {
    screens: {
      ResetPassword: {
        path: 'reset-password',
        parse: {
          token: (token) => token,
        },
      },
      PaymentResult: {
        path: 'payment-return',
        parse: {
          checkout_session_id: parseCheckoutSessionId,
          status: parsePaymentReturnStatus,
        },
      },
    },
  },
};
