import type { Locale } from '@/lib/i18n';
import type { Alert } from '@/types';

type AlertUiKey =
  | 'pageTitle'
  | 'pageSubtitle'
  | 'searchPlaceholder'
  | 'severity'
  | 'status'
  | 'all'
  | 'description'
  | 'site'
  | 'device'
  | 'evse'
  | 'unassigned'
  | 'model'
  | 'serialNumber'
  | 'physicalReference'
  | 'occurredAt'
  | 'viewSite'
  | 'viewDevice'
  | 'technicalDetails'
  | 'alertCode'
  | 'rawMessage'
  | 'messageParams'
  | 'noTechnicalDetails'
  | 'acknowledge'
  | 'resolve'
  | 'acknowledgedNotice'
  | 'acknowledgeFailed'
  | 'resolvedNotice'
  | 'resolveFailed'
  | 'loading'
  | 'loadFailed'
  | 'empty';

const alertUi: Record<Locale, Record<AlertUiKey, string>> = {
  'zh-CN': {
    pageTitle: '告警管理',
    pageSubtitle: '查看和处理系统告警',
    searchPlaceholder: '搜索告警、站点、OCPP Identity 或 EVSE…',
    severity: '严重程度',
    status: '状态',
    all: '全部',
    description: '描述',
    site: '站点',
    device: 'OCPP Identity',
    evse: 'EVSE',
    unassigned: '未关联',
    model: '型号',
    serialNumber: '序列号',
    physicalReference: '物理位置',
    occurredAt: '发生时间',
    viewSite: '查看站点',
    viewDevice: '查看设备',
    technicalDetails: '原始技术信息',
    alertCode: '告警代码',
    rawMessage: '原始消息',
    messageParams: '消息参数',
    noTechnicalDetails: '无原始技术信息',
    acknowledge: '确认',
    resolve: '解决',
    acknowledgedNotice: '告警已确认',
    acknowledgeFailed: '确认失败',
    resolvedNotice: '告警已解决',
    resolveFailed: '解决失败',
    loading: '加载中…',
    loadFailed: '加载失败，请刷新页面重试',
    empty: '没有找到告警',
  },
  en: {
    pageTitle: 'Alert management',
    pageSubtitle: 'View and handle system alerts',
    searchPlaceholder: 'Search alerts, sites, OCPP Identity, or EVSE…',
    severity: 'Severity',
    status: 'Status',
    all: 'All',
    description: 'Description',
    site: 'Site',
    device: 'OCPP Identity',
    evse: 'EVSE',
    unassigned: 'Unassigned',
    model: 'Model',
    serialNumber: 'Serial number',
    physicalReference: 'Physical reference',
    occurredAt: 'Occurred at',
    viewSite: 'View site',
    viewDevice: 'View device',
    technicalDetails: 'Raw technical information',
    alertCode: 'Alert code',
    rawMessage: 'Raw message',
    messageParams: 'Message parameters',
    noTechnicalDetails: 'No raw technical information',
    acknowledge: 'Acknowledge',
    resolve: 'Resolve',
    acknowledgedNotice: 'Alert acknowledged',
    acknowledgeFailed: 'Acknowledgement failed',
    resolvedNotice: 'Alert resolved',
    resolveFailed: 'Resolution failed',
    loading: 'Loading…',
    loadFailed: 'Failed to load. Refresh the page and try again.',
    empty: 'No alerts found',
  },
  es: {
    pageTitle: 'Gestión de alertas',
    pageSubtitle: 'Consulta y gestiona alertas del sistema',
    searchPlaceholder: 'Buscar alertas, sitios, identidad OCPP o EVSE…',
    severity: 'Severidad',
    status: 'Estado',
    all: 'Todas',
    description: 'Descripción',
    site: 'Sitio',
    device: 'Identidad OCPP',
    evse: 'EVSE',
    unassigned: 'Sin asociar',
    model: 'Modelo',
    serialNumber: 'Número de serie',
    physicalReference: 'Referencia física',
    occurredAt: 'Ocurrió el',
    viewSite: 'Ver sitio',
    viewDevice: 'Ver equipo',
    technicalDetails: 'Información técnica original',
    alertCode: 'Código de alerta',
    rawMessage: 'Mensaje original',
    messageParams: 'Parámetros del mensaje',
    noTechnicalDetails: 'No hay información técnica original',
    acknowledge: 'Confirmar',
    resolve: 'Resolver',
    acknowledgedNotice: 'Alerta confirmada',
    acknowledgeFailed: 'No se pudo confirmar la alerta',
    resolvedNotice: 'Alerta resuelta',
    resolveFailed: 'No se pudo resolver la alerta',
    loading: 'Cargando…',
    loadFailed: 'No se pudo cargar. Actualiza la página e inténtalo de nuevo.',
    empty: 'No se encontraron alertas',
  },
};

const severityLabels: Record<Locale, Record<string, string>> = {
  'zh-CN': { critical: '严重', warning: '警告', info: '信息' },
  en: { critical: 'Critical', warning: 'Warning', info: 'Information' },
  es: { critical: 'Crítica', warning: 'Advertencia', info: 'Información' },
};

const statusLabels: Record<Locale, Record<string, string>> = {
  'zh-CN': { pending: '待处理', acknowledged: '已确认', resolved: '已解决' },
  en: { pending: 'Pending', acknowledged: 'Acknowledged', resolved: 'Resolved' },
  es: { pending: 'Pendiente', acknowledged: 'Confirmada', resolved: 'Resuelta' },
};

const alertMessages: Record<Locale, Record<string, { title: string; description: string }>> = {
  'zh-CN': {
    'charger.offline.heartbeat_timeout': { title: '充电桩心跳超时', description: '充电桩未在预期时间内发送心跳。' },
    'charger.offline.websocket_disconnected': { title: '充电桩连接中断', description: '充电桩的 OCPP 连接已意外断开。' },
    'charger.faulted': { title: '充电桩故障', description: '充电桩报告了需要处理的故障。' },
    'device.event': { title: '设备事件', description: '设备报告了需要关注的事件。' },
    manual: { title: '人工告警', description: '运营人员创建的告警需要处理。' },
    unknown: { title: '系统告警', description: '收到无法识别的告警类型，请查看原始技术信息。' },
  },
  en: {
    'charger.offline.heartbeat_timeout': { title: 'Charger heartbeat timeout', description: 'The charger did not send a heartbeat within the expected interval.' },
    'charger.offline.websocket_disconnected': { title: 'Charger connection lost', description: 'The charger’s OCPP connection ended unexpectedly.' },
    'charger.faulted': { title: 'Charger fault', description: 'The charger reported a fault that requires attention.' },
    'device.event': { title: 'Device event', description: 'The device reported an event that requires attention.' },
    manual: { title: 'Manual alert', description: 'An operator-created alert requires attention.' },
    unknown: { title: 'System alert', description: 'An unrecognized alert type was received. Review the raw technical information.' },
  },
  es: {
    'charger.offline.heartbeat_timeout': { title: 'Tiempo de espera del latido agotado', description: 'El cargador no envió un latido dentro del intervalo esperado.' },
    'charger.offline.websocket_disconnected': { title: 'Conexión del cargador interrumpida', description: 'La conexión OCPP del cargador terminó de forma inesperada.' },
    'charger.faulted': { title: 'Fallo del cargador', description: 'El cargador informó de un fallo que requiere atención.' },
    'device.event': { title: 'Evento del equipo', description: 'El equipo informó de un evento que requiere atención.' },
    manual: { title: 'Alerta manual', description: 'Una alerta creada por un operador requiere atención.' },
    unknown: { title: 'Alerta del sistema', description: 'Se recibió un tipo de alerta desconocido. Revisa la información técnica original.' },
  },
};

export function alertText(locale: Locale, key: AlertUiKey): string {
  return alertUi[locale][key];
}

export function alertSeverityLabel(locale: Locale, severity: string): string {
  return severityLabels[locale][severity] || severity;
}

export function alertStatusLabel(locale: Locale, status: string): string {
  return statusLabels[locale][status] || status;
}

export function localizedAlertMessage(locale: Locale, alert: Alert) {
  const code = alert.alert_code || 'unknown';
  const message = alertMessages[locale][code] || alertMessages[locale].unknown;
  const timeout = alert.message_params?.timeout_seconds;

  if (code !== 'charger.offline.heartbeat_timeout' || (typeof timeout !== 'number' && typeof timeout !== 'string')) {
    return message;
  }

  const seconds = String(timeout);
  const description = locale === 'zh-CN'
    ? `充电桩已超过 ${seconds} 秒未发送心跳。`
    : locale === 'es'
      ? `El cargador no ha enviado un latido durante más de ${seconds} segundos.`
      : `The charger has not sent a heartbeat for more than ${seconds} seconds.`;

  return { ...message, description };
}

export function alertRawMessage(alert: Alert): string | null {
  return alert.raw_message?.trim()
    || alert.description?.trim()
    || (!alert.alert_code ? alert.title?.trim() : '')
    || null;
}

function sanitizeMessageParam(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sanitizeMessageParam);
  }

  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([key]) => {
          const normalizedKey = key.toLowerCase();
          return normalizedKey !== 'id' && !normalizedKey.endsWith('_id');
        })
        .map(([key, nestedValue]) => [key, sanitizeMessageParam(nestedValue)])
    );
  }

  return value;
}

export function sanitizedAlertMessageParams(
  params: Record<string, unknown> | null | undefined
): Record<string, unknown> {
  if (!params) return {};
  return sanitizeMessageParam(params) as Record<string, unknown>;
}

export function alertDateLocale(locale: Locale): string {
  return locale === 'en' ? 'en-US' : locale === 'es' ? 'es-CO' : 'zh-CN';
}
