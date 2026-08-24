import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  classifyCheckoutQueryError,
  createCheckoutSession,
  getCheckoutSession,
} from '../../api/payments';
import type {
  CheckoutSessionResponse,
  CreateCheckoutSessionRequest,
  CreateCheckoutSessionResponse,
  PaymentCheckoutPurpose,
} from '../../types';

const PENDING_CHECKOUT_KEY = '@eslatin/payment_checkout_recovery';
const MAX_REFERENCE_LENGTH = 256;

export type PendingCheckoutSource = 'add_payment' | 'wallet_top_up' | 'charging_direct' | 'unpaid_charge';

export type CheckoutRecoveryKind =
  | 'resolved'
  | 'expired_or_missing'
  | 'already_submitted'
  | 'temporarily_unavailable'
  | 'network_unknown';

export interface CheckoutRecoveryResult {
  kind: CheckoutRecoveryKind;
  session: CheckoutSessionResponse | null;
  purpose?: PaymentCheckoutPurpose;
  source?: PendingCheckoutSource;
}

export interface PendingCheckoutReference {
  checkoutSessionId: string;
  purpose: PaymentCheckoutPurpose;
  expiresAt: string;
  source?: PendingCheckoutSource;
}

const resolveInFlight = new Map<string, Promise<CheckoutRecoveryResult>>();

const sourceForPurpose = (purpose: PaymentCheckoutPurpose): PendingCheckoutSource | undefined => {
  if (purpose === 'save_card') return 'add_payment';
  if (purpose === 'wallet_top_up') return 'wallet_top_up';
  if (purpose === 'charging_direct') return 'charging_direct';
  if (purpose === 'unpaid_charge') return 'unpaid_charge';
  return undefined;
};

const isSafeReference = (value: unknown): value is string =>
  typeof value === 'string' && value.trim().length > 0 && value.length <= MAX_REFERENCE_LENGTH;

const saveReference = async (reference: PendingCheckoutReference): Promise<void> => {
  await AsyncStorage.setItem(PENDING_CHECKOUT_KEY, JSON.stringify(reference));
};

export async function trackCheckoutSession(
  session: Pick<CreateCheckoutSessionResponse, 'checkout_session_id' | 'purpose' | 'expires_at'>,
): Promise<PendingCheckoutReference> {
  const reference: PendingCheckoutReference = {
    checkoutSessionId: session.checkout_session_id,
    purpose: session.purpose,
    expiresAt: session.expires_at,
    source: sourceForPurpose(session.purpose),
  };
  await saveReference(reference);
  return reference;
}

export async function startCheckoutSession(
  request: Omit<CreateCheckoutSessionRequest, 'idempotency_key' | 'return_url'> & {
    idempotency_key?: string;
    return_url?: string;
  },
): Promise<CreateCheckoutSessionResponse> {
  const session = await createCheckoutSession(request);
  await trackCheckoutSession(session);
  return session;
}

const applyResolvedSession = async (
  session: CheckoutSessionResponse,
  pending: PendingCheckoutReference | null,
): Promise<CheckoutRecoveryResult> => {
  const source = pending?.source ?? sourceForPurpose(session.purpose);
  if (session.status === 'approved' || session.status === 'declined' ||
      session.status === 'expired' || session.status === 'error') {
    await clearPendingCheckoutSession();
  } else {
    await saveReference({
      checkoutSessionId: session.id,
      purpose: session.purpose,
      expiresAt: session.expires_at,
      source,
    });
  }
  return { kind: 'resolved', session, purpose: session.purpose, source };
};

const resolveCheckoutSessionOnce = async (
  checkoutSessionId: string,
): Promise<CheckoutRecoveryResult> => {
  const pending = await getPendingCheckoutSession();
  try {
    const session = await getCheckoutSession(checkoutSessionId);
    return applyResolvedSession(session, pending);
  } catch (error) {
    const kind = classifyCheckoutQueryError(error);
    if (kind === 'expired_or_missing') {
      await clearPendingCheckoutSession();
      return {
        kind,
        session: null,
        purpose: pending?.purpose,
        source: pending?.source,
      };
    }

    if (kind === 'already_submitted') {
      try {
        const session = await getCheckoutSession(checkoutSessionId);
        return applyResolvedSession(session, pending);
      } catch (followUpError) {
        if (classifyCheckoutQueryError(followUpError) === 'expired_or_missing') {
          await clearPendingCheckoutSession();
          return {
            kind: 'expired_or_missing',
            session: null,
            purpose: pending?.purpose,
            source: pending?.source,
          };
        }
        return {
          kind: 'already_submitted',
          session: null,
          purpose: pending?.purpose,
          source: pending?.source,
        };
      }
    }

    return {
      kind,
      session: null,
      purpose: pending?.purpose,
      source: pending?.source,
    };
  }
};

/** Deep links, foreground recovery, polling and manual refresh share one read-only query. */
export function resolveCheckoutSession(
  checkoutSessionId: string,
): Promise<CheckoutRecoveryResult> {
  const existing = resolveInFlight.get(checkoutSessionId);
  if (existing) return existing;

  const request = resolveCheckoutSessionOnce(checkoutSessionId).finally(() => {
    resolveInFlight.delete(checkoutSessionId);
  });
  resolveInFlight.set(checkoutSessionId, request);
  return request;
}

export async function getPendingCheckoutSession(): Promise<PendingCheckoutReference | null> {
  const raw = await AsyncStorage.getItem(PENDING_CHECKOUT_KEY);
  if (!raw) return null;

  try {
    const value = JSON.parse(raw) as Partial<PendingCheckoutReference>;
    if (!isSafeReference(value.checkoutSessionId) ||
        !isSafeReference(value.expiresAt) ||
        !['save_card', 'wallet_top_up', 'charging_direct', 'unpaid_charge'].includes(value.purpose ?? '')) {
      await AsyncStorage.removeItem(PENDING_CHECKOUT_KEY);
      return null;
    }
    const purpose = value.purpose as PaymentCheckoutPurpose;
    const source = value.source === 'add_payment' ||
      value.source === 'wallet_top_up' ||
      value.source === 'charging_direct'
      ? value.source
      : sourceForPurpose(purpose);
    return {
      checkoutSessionId: value.checkoutSessionId,
      purpose,
      expiresAt: value.expiresAt,
      source,
    };
  } catch {
    await AsyncStorage.removeItem(PENDING_CHECKOUT_KEY);
    return null;
  }
}

export async function clearPendingCheckoutSession(): Promise<void> {
  await AsyncStorage.removeItem(PENDING_CHECKOUT_KEY);
}

export const isCheckoutTerminal = (status: CheckoutSessionResponse['status']): boolean =>
  status === 'approved' || status === 'declined' || status === 'expired' || status === 'error';
