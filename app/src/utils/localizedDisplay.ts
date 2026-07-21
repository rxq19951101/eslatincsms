import type { AppLocale, I18nKeys } from '../i18n';
import type { WalletTransaction } from '../types';
import type { ChargingFailure } from '../store/slices/chargingSlice';

const LOCALE_TAGS: Record<AppLocale, string> = {
  es: 'es-CO',
  en: 'en-US',
  zh: 'zh-CN',
};

/** Format API timestamps in the language currently selected in the App. */
export function formatDateTime(value: string | null | undefined, locale: AppLocale): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(LOCALE_TAGS[locale], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Never fall back to an internal database ID in user-visible charger labels. */
export function publicChargerIdentity(
  value: { ocpp_identity?: string | null } | null | undefined,
  fallback = '—'
): string {
  const identity = value?.ocpp_identity?.trim();
  return identity || fallback;
}

/**
 * Wallet descriptions come from structured fields. Backend descriptions and
 * references may contain internal IDs or a language chosen by the server, so
 * neither is rendered directly.
 */
export function localizeWalletTransaction(item: WalletTransaction, t: I18nKeys): string {
  const kind = `${item.type || ''}:${item.reference || ''}`.toLowerCase();
  let label = t.wallet.transactionLabel;

  if (kind.includes('top_up') || kind.includes('topup') || kind.includes('payment')) {
    label = t.wallet.topUpLabel;
  } else if (kind.includes('refund')) {
    label = t.wallet.refundLabel;
  } else if (kind.includes('adjust')) {
    label = t.wallet.adjustmentLabel;
  } else if (kind.includes('charge') || kind.includes('charging')) {
    label = t.wallet.chargeLabel;
  }

  const chargerLabel = item.charge_point_name || item.ocpp_identity;
  return chargerLabel ? `${label} · ${chargerLabel}` : label;
}

/** Convert stable API error semantics into the currently selected language. */
export function localizeChargingFailure(
  failure: ChargingFailure | null | undefined,
  t: I18nKeys
): string | null {
  if (!failure) return null;
  const code = String(failure.code || '').toUpperCase();

  if (failure.operation === 'meter') return t.charging.meterLoadFailed;
  if (failure.operation === 'active' || failure.operation === 'restore') {
    return t.charging.sessionLoadFailed;
  }
  if (failure.operation === 'stop') return t.charging.stopFailedGeneric;
  if (failure.status === 504 || code.includes('TIMEOUT')) return t.charging.startTimeout;
  if (failure.status === 409 || code.includes('REJECT')) return t.charging.startRejected;
  if (failure.status === 402 || code.includes('BALANCE')) return t.charging.insufficientBalance;
  return t.charging.startFailed;
}
