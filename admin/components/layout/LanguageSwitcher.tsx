'use client';

import { useI18n, Locale } from '@/lib/i18n';

export function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n();
  return (
    <label className="flex items-center gap-2 text-xs text-slate-400" title={t('language')}>
      <span className="sr-only">{t('language')}</span>
      <select
        value={locale}
        onChange={(event) => setLocale(event.target.value as Locale)}
        className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-slate-200 outline-none"
        aria-label={t('language')}
      >
        <option value="zh-CN">{t('chinese')}</option>
        <option value="en">{t('english')}</option>
        <option value="es">{t('spanish')}</option>
      </select>
    </label>
  );
}
