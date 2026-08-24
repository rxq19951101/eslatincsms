'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { apiGet } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { useI18n } from '@/lib/i18n';

export type GeocodingSuggestion = {
  display_name: string;
  lat: number;
  lon: number;
  address?: Record<string, unknown>;
};

export function buildGeocodingSearchUrl(q: string, limit = 5) {
  const params = new URLSearchParams();
  params.set('q', q);
  params.set('limit', String(limit));
  return `/api/v1/geocoding/search?${params.toString()}`;
}

export default function AddressAutocomplete(props: {
  value: string;
  onChange: (v: string) => void;
  onSelect: (s: GeocodingSuggestion) => void;
  placeholder?: string;
  disabled?: boolean;
  limit?: number;
  className?: string;
}) {
  const { value, onChange, onSelect, placeholder, disabled, limit = 5, className } = props;
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [items, setItems] = useState<GeocodingSuggestion[]>([]);

  const rootRef = useRef<HTMLDivElement | null>(null);
  const debounceRef = useRef<number | null>(null);

  const trimmed = useMemo(() => (value || '').trim(), [value]);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  useEffect(() => {
    setErrorText(null);

    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }

    if (!trimmed || trimmed.length < 3) {
      setItems([]);
      setOpen(false);
      return;
    }

    debounceRef.current = window.setTimeout(async () => {
      setLoading(true);
      try {
        const url = buildGeocodingSearchUrl(trimmed, limit);
        const data = await apiGet<GeocodingSuggestion[]>(url);
        setItems(Array.isArray(data) ? data : []);
        setOpen(true);
      } catch (e) {
        setItems([]);
        setOpen(false);
        setErrorText(e instanceof Error ? e.message : t('地址搜索失败'));
      } finally {
        setLoading(false);
      }
    }, 400);

    return () => {
      if (debounceRef.current) {
        window.clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
    };
  }, [trimmed, limit, t]);

  return (
    <div ref={rootRef} className="relative">
      <Input
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
        }}
        onFocus={() => {
          if (items.length > 0) setOpen(true);
        }}
        placeholder={placeholder}
        disabled={disabled}
        className={className}
      />

      {loading && (
        <div className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">
          {t('搜索中...')}
        </div>
      )}

      {errorText && (
        <div className="mt-2 text-xs text-red-300">
          {errorText}
        </div>
      )}

      {open && items.length > 0 && (
        <div className="absolute z-50 mt-2 w-full rounded-md border border-slate-700 bg-slate-900 shadow-lg max-h-[280px] overflow-auto">
          {items.map((it, idx) => (
            <button
              key={`${it.display_name}-${idx}`}
              type="button"
              className="w-full text-left px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"
              onClick={() => {
                onSelect(it);
                setOpen(false);
              }}
            >
              <div className="text-slate-100">{it.display_name}</div>
              <div className="text-xs text-slate-400 mt-1">
                {it.lat.toFixed(6)}, {it.lon.toFixed(6)}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
