import type { I18nKeys } from '../i18n';

/** Translate backend/OCPP enum values without changing their API representation. */
export function localizeStatus(value: string | null | undefined, t: I18nKeys): string {
  const normalized = String(value || 'unknown').replace(/[\s_-]/g, '').toLowerCase();
  const labels: Record<string, string> = {
    available: t.status.available, preparing: t.status.preparing, charging: t.status.charging,
    suspendedev: t.status.suspended, suspendedevse: t.status.suspended,
    finishing: t.status.finishing, reserved: t.status.reserved,
    unavailable: t.status.unavailable, faulted: t.status.faulted,
    offline: t.status.offline, online: t.status.online, active: t.status.active,
    completed: t.status.completed, stopped: t.status.stopped,
    cancelled: t.status.cancelled, canceled: t.status.cancelled,
    failed: t.status.failed, unknown: t.status.unknown,
  };
  return labels[normalized] || t.status.unknown;
}

