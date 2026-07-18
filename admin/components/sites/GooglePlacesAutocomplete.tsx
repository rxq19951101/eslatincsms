'use client';

import { useEffect, useRef, useState } from 'react';
import { Loader } from '@googlemaps/js-api-loader';
import { Input } from '@/components/ui/input';
import { useI18n } from '@/lib/i18n';

interface GooglePlacesAutocompleteProps {
  value: string;
  onChange: (value: string) => void;
  onSelect: (result: { address: string; lat: number; lng: number }) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export default function GooglePlacesAutocomplete(props: GooglePlacesAutocompleteProps) {
  const { value, onChange, onSelect, placeholder, disabled, className } = props;
  const { t, locale } = useI18n();

  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<google.maps.places.AutocompletePrediction[]>([]);
  const [error, setError] = useState<string | null>(null);

  const rootRef = useRef<HTMLDivElement>(null);
  const debounceTimer = useRef<NodeJS.Timeout | null>(null);

  // Google Maps 服务引用
  const sessionTokenRef = useRef<google.maps.places.AutocompleteSessionToken | null>(null);
  const autocompleteServiceRef = useRef<google.maps.places.AutocompleteService | null>(null);
  const placesServiceRef = useRef<google.maps.places.PlacesService | null>(null);

  // 初始化 Google Maps API
  useEffect(() => {
    const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
    if (!apiKey) {
      setError(t('Google Maps API 密钥未配置'));
      return;
    }

    const loader = new Loader({
      apiKey,
      version: 'weekly',
      libraries: ['places'],
      language: locale === 'es' ? 'es' : locale === 'en' ? 'en' : 'zh-CN',
      region: 'CO',
    });

    loader
      .load()
      .then(() => {
        // 初始化 Autocomplete Service
        autocompleteServiceRef.current = new google.maps.places.AutocompleteService();

        // PlacesService 需要一个 DOM 元素（创建隐藏的 div）
        const div = document.createElement('div');
        placesServiceRef.current = new google.maps.places.PlacesService(div);
      })
      .catch((err) => {
        console.error('Google Maps API 加载失败:', err);
        setError(t('地图服务加载失败'));
      });
  }, [locale, t]);

  // 点击外部关闭下拉框
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Debounce + Session Token 实现
  useEffect(() => {
    setError(null);

    // 清除上一个定时器
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current);
    }

    const trimmed = value.trim();
    if (trimmed.length < 3) {
      setItems([]);
      setOpen(false);
      return;
    }

    // 防抖：300ms 延迟
    debounceTimer.current = setTimeout(() => {
      if (!autocompleteServiceRef.current) {
        setError(t('地图服务未就绪'));
        return;
      }

      // 创建新的 Session Token（如果不存在）
      if (!sessionTokenRef.current) {
        sessionTokenRef.current = new google.maps.places.AutocompleteSessionToken();
      }

      setLoading(true);

      // 调用 Autocomplete API（传入 Session Token）
      autocompleteServiceRef.current.getPlacePredictions(
        {
          input: trimmed,
          sessionToken: sessionTokenRef.current, // 关键：Session Token
          componentRestrictions: { country: 'co' } // 限制哥伦比亚
        },
        (predictions, status) => {
          setLoading(false);

          if (status === google.maps.places.PlacesServiceStatus.OK && predictions) {
            setItems(predictions);
            setOpen(true);
          } else if (status === google.maps.places.PlacesServiceStatus.ZERO_RESULTS) {
            setItems([]);
            setOpen(false);
          } else {
            console.error('Autocomplete 失败:', status);
            setError(t('地址搜索失败'));
            setItems([]);
            setOpen(false);
          }
        }
      );
    }, 300); // 300ms 防抖

    return () => {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }
    };
  }, [value]);

  // 用户选中某个建议
  const handleSelect = (prediction: google.maps.places.AutocompletePrediction) => {
    if (!placesServiceRef.current || !sessionTokenRef.current) {
      setError(t('地图服务未就绪'));
      return;
    }

    setLoading(true);

    // 使用相同的 Session Token 查询详情
    placesServiceRef.current.getDetails(
      {
        placeId: prediction.place_id,
        sessionToken: sessionTokenRef.current, // 关键：使用相同的 token
        fields: ['geometry', 'formatted_address']
      },
      (place, status) => {
        setLoading(false);

        if (status === google.maps.places.PlacesServiceStatus.OK && place?.geometry?.location) {
          const lat = place.geometry.location.lat();
          const lng = place.geometry.location.lng();
          const address = place.formatted_address || prediction.description;

          onSelect({ address, lat, lng });
          setOpen(false);

          // 查询完成后销毁 Session Token
          sessionTokenRef.current = null;
        } else {
          console.error('Place Details 失败:', status);
          setError(t('获取地址详情失败'));
        }
      }
    );
  };

  return (
    <div ref={rootRef} className="relative">
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => items.length > 0 && setOpen(true)}
        placeholder={placeholder}
        disabled={disabled}
        className={className}
      />

      {loading && (
        <div className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">
          {t('搜索中...')}
        </div>
      )}

      {error && <div className="mt-2 text-xs text-red-300">{error}</div>}

      {open && items.length > 0 && (
        <div className="absolute z-50 mt-2 w-full rounded-md border border-slate-700 bg-slate-900 shadow-lg max-h-[280px] overflow-auto">
          {items.map((item) => (
            <button
              key={item.place_id}
              type="button"
              className="w-full text-left px-3 py-2 text-sm text-slate-200 hover:bg-slate-800 transition-colors"
              onClick={() => handleSelect(item)}
            >
              <div className="text-slate-100 font-medium">
                {item.structured_formatting.main_text}
              </div>
              <div className="text-xs text-slate-400 mt-1">
                {item.structured_formatting.secondary_text}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
