export { es } from './es';
export type { I18nKeys } from './es';
export { en } from './en';
export { zh } from './zh';
export {
  I18nProvider,
  useI18n,
  getT,
  getLocale,
  detectDeviceLocale,
  type AppLocale,
} from './I18nProvider';

import { es } from './es';

/**
 * @deprecated Prefer `useI18n().t` in React components so language switches re-render.
 * Kept as default Spanish for non-React / early-boot fallbacks.
 */
export const t = es;
