/**
 * Etiquetas de rieles de pago (Colombia: PSE, Nequi, Daviplata, etc.)
 */
import type { PaymentRail } from '../types';
import { getT } from '../i18n';
import type { I18nKeys } from '../i18n';

export function getPaymentRailLabels(
  dict?: I18nKeys
): Record<PaymentRail, string> {
  const t = dict ?? getT();
  return {
    card: t.paymentRails.card,
    wallet: t.paymentRails.wallet,
    pse: t.paymentRails.pse,
    nequi: t.paymentRails.nequi,
    daviplata: t.paymentRails.daviplata,
    other: t.paymentRails.other,
  };
}

/** @deprecated Use getPaymentRailLabels() so locale can change */
export const PAYMENT_RAIL_LABELS: Record<PaymentRail, string> = getPaymentRailLabels();
