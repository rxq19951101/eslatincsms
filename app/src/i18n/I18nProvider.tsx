import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Localization from 'expo-localization';
import { es, type I18nKeys } from './es';
import { en } from './en';
import { zh } from './zh';

export type AppLocale = 'es' | 'en' | 'zh';

const STORAGE_KEY = '@eslatin/locale';

const dictionaries: Record<AppLocale, I18nKeys> = { es, en, zh };

export function detectDeviceLocale(): AppLocale {
  try {
    const tag = Localization.getLocales()?.[0]?.languageCode?.toLowerCase() || 'es';
    if (tag.startsWith('zh')) return 'zh';
    if (tag.startsWith('en')) return 'en';
    if (tag.startsWith('es')) return 'es';
  } catch {
    // Expo Go / native module unavailable in some test environments
  }
  return 'es';
}

type I18nContextValue = {
  locale: AppLocale;
  t: I18nKeys;
  setLocale: (locale: AppLocale) => void;
  ready: boolean;
};

const I18nContext = createContext<I18nContextValue | null>(null);

/** Fallback for non-React modules before provider mounts */
let currentT: I18nKeys = es;
let currentLocale: AppLocale = 'es';

export function getT(): I18nKeys {
  return currentT;
}

export function getLocale(): AppLocale {
  return currentLocale;
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<AppLocale>('es');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const saved = await AsyncStorage.getItem(STORAGE_KEY);
        const next: AppLocale =
          saved === 'es' || saved === 'en' || saved === 'zh'
            ? saved
            : detectDeviceLocale();
        if (!cancelled) {
          currentLocale = next;
          currentT = dictionaries[next];
          setLocaleState(next);
        }
      } catch {
        const next = detectDeviceLocale();
        if (!cancelled) {
          currentLocale = next;
          currentT = dictionaries[next];
          setLocaleState(next);
        }
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setLocale = useCallback((next: AppLocale) => {
    currentLocale = next;
    currentT = dictionaries[next];
    setLocaleState(next);
    void AsyncStorage.setItem(STORAGE_KEY, next);
  }, []);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      t: dictionaries[locale],
      setLocale,
      ready,
    }),
    [locale, setLocale, ready]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    return {
      locale: currentLocale,
      t: currentT,
      setLocale: () => {},
      ready: true,
    };
  }
  return ctx;
}
