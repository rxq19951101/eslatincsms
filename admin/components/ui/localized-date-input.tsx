'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isAfter,
  isBefore,
  isSameDay,
  isSameMonth,
  isValid,
  parseISO,
  startOfMonth,
  startOfWeek,
  subMonths,
  type Locale as DateFnsLocale,
} from 'date-fns';
import { enUS, es, zhCN } from 'date-fns/locale';
import { CalendarDays, ChevronLeft, ChevronRight, X } from 'lucide-react';

import { useI18n, type Locale } from '@/lib/i18n';
import { cn } from '@/lib/utils';

const DATE_LOCALES: Record<Locale, DateFnsLocale> = { 'zh-CN': zhCN, en: enUS, es };

function parsedDate(value?: string): Date | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = parseISO(value);
  return isValid(date) ? date : null;
}

interface LocalizedDateInputProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  min?: string;
  max?: string;
  'aria-label': string;
  className?: string;
  testId?: string;
}

export function LocalizedDateInput({
  id,
  value,
  onChange,
  min,
  max,
  'aria-label': ariaLabel,
  className,
  testId,
}: LocalizedDateInputProps) {
  const { locale, t } = useI18n();
  const dateLocale = DATE_LOCALES[locale];
  const selectedDate = parsedDate(value);
  const minDate = parsedDate(min);
  const maxDate = parsedDate(max);
  const [open, setOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState(() => selectedDate ?? new Date());
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [open]);

  const days = useMemo(() => {
    const monthStart = startOfMonth(visibleMonth);
    return eachDayOfInterval({
      start: startOfWeek(monthStart, { locale: dateLocale }),
      end: endOfWeek(endOfMonth(monthStart), { locale: dateLocale }),
    });
  }, [dateLocale, visibleMonth]);

  const weekdays = days.slice(0, 7).map((day) => format(day, 'EEEEE', { locale: dateLocale }));
  const previousMonth = subMonths(visibleMonth, 1);
  const nextMonth = addMonths(visibleMonth, 1);
  const previousDisabled = Boolean(minDate && isBefore(endOfMonth(previousMonth), minDate));
  const nextDisabled = Boolean(maxDate && isAfter(startOfMonth(nextMonth), maxDate));
  const isDateDisabled = (date: Date) =>
    Boolean((minDate && isBefore(date, minDate)) || (maxDate && isAfter(date, maxDate)));

  const selectDate = (date: Date) => {
    if (isDateDisabled(date)) return;
    onChange(format(date, 'yyyy-MM-dd'));
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        id={id}
        type="button"
        data-testid={testId}
        aria-label={ariaLabel}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => {
          if (!open) setVisibleMonth(selectedDate ?? new Date());
          setOpen((current) => !current);
        }}
        className={cn(
          'flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-left text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
          !selectedDate && 'text-muted-foreground',
          className,
        )}
      >
        <span>{selectedDate ? format(selectedDate, 'P', { locale: dateLocale }) : t('date.placeholder')}</span>
        <CalendarDays className="h-4 w-4 text-slate-400" aria-hidden="true" />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={`${t('date.selectDate')}: ${ariaLabel}`}
          className="absolute left-0 z-50 mt-2 w-[19rem] rounded-lg border border-slate-600 bg-slate-800 p-3 text-slate-100 shadow-2xl"
        >
          <div className="mb-3 flex items-center justify-between">
            <button
              type="button"
              aria-label={t('date.previousMonth')}
              disabled={previousDisabled}
              onClick={() => setVisibleMonth(previousMonth)}
              className="rounded-md p-2 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-30"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="font-medium capitalize">{format(visibleMonth, 'LLLL yyyy', { locale: dateLocale })}</span>
            <button
              type="button"
              aria-label={t('date.nextMonth')}
              disabled={nextDisabled}
              onClick={() => setVisibleMonth(nextMonth)}
              className="rounded-md p-2 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-30"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-7 gap-1 text-center text-xs text-slate-400" aria-hidden="true">
            {weekdays.map((weekday, index) => <span key={`${weekday}-${index}`}>{weekday}</span>)}
          </div>
          <div className="mt-1 grid grid-cols-7 gap-1">
            {days.map((day) => {
              const disabled = isDateDisabled(day);
              const selected = Boolean(selectedDate && isSameDay(day, selectedDate));
              return (
                <button
                  key={format(day, 'yyyy-MM-dd')}
                  type="button"
                  aria-label={format(day, 'PPPP', { locale: dateLocale })}
                  aria-pressed={selected}
                  disabled={disabled}
                  onClick={() => selectDate(day)}
                  className={cn(
                    'h-9 rounded-md text-sm hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-25',
                    !isSameMonth(day, visibleMonth) && 'text-slate-500',
                    selected && 'bg-blue-600 font-semibold text-white hover:bg-blue-600',
                  )}
                >
                  {format(day, 'd')}
                </button>
              );
            })}
          </div>

          <div className="mt-3 flex justify-end border-t border-slate-700 pt-2">
            <button
              type="button"
              disabled={!value}
              onClick={() => { onChange(''); setOpen(false); }}
              className="flex items-center gap-1 rounded-md px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-700 disabled:opacity-40"
            >
              <X className="h-3.5 w-3.5" />
              {t('date.clear')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
