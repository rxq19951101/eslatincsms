// API 基础 URL
// 优先级: NEXT_PUBLIC_CSMS_HTTP > NEXT_PUBLIC_API_BASE_URL > 默认值
export const API_BASE_URL = process.env.NEXT_PUBLIC_CSMS_HTTP || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:9000';

// API 端点
export const API_ENDPOINTS = {
  // 认证
  AUTH_LOGIN: '/api/v1/admin/auth/login',
  AUTH_REFRESH: '/api/v1/admin/auth/refresh',
  AUTH_LOGOUT: '/api/v1/admin/auth/logout',
  AUTH_ME: '/api/v1/admin/auth/me',
  AUTH_ME_PERMISSIONS: '/api/v1/admin/auth/me/permissions',
  AUTH_SET_DEFAULT_TENANT: '/api/v1/admin/auth/me/default-tenant',
  
  // Dashboard
  DASHBOARD_SUMMARY: '/api/v1/dashboard/summary',
  DASHBOARD_TRENDS: '/api/v1/dashboard/trends',
  DASHBOARD_SITES: '/api/v1/dashboard/sites',
  
  // 充电桩
  CHARGERS: '/api/v1/chargers',
  CHARGER_DETAIL: (id: string) => `/api/v1/chargers/${id}`,
  CHARGER_PRICING: (id: string) => `/api/v1/chargers/${id}/pricing`,

  // 站点（Site）
  SITES: '/api/v1/sites',
  SITE_DETAIL: (id: string) => `/api/v1/sites/${id}`,
  SITE_PRICING: (id: string) => `/api/v1/sites/${id}/pricing`,
  SITE_BINDABLE_CHARGE_POINTS: (id: string) => `/api/v1/sites/${id}/bindable-charge-points`,
  SITE_BIND_CHARGE_POINTS: (id: string) => `/api/v1/sites/${id}/bind-charge-points`,
  SITE_CREATE_CHARGE_POINT: (id: string) => `/api/v1/sites/${id}/charge-points`,
  
  // 交易
  TRANSACTIONS: '/api/v1/transactions',
  TRANSACTIONS_ACTIVE: '/api/v1/transactions/active',
  
  // 统计
  STATISTICS_REVENUE: '/api/v1/admin/statistics/revenue',
  STATISTICS_ENERGY: '/api/v1/admin/statistics/energy',
  STATISTICS_ORDERS: '/api/v1/admin/statistics/orders',
  STATISTICS_EXPORT: '/api/v1/admin/statistics/export',
  
  // 告警
  ALERTS: '/api/v1/admin/alerts',
  ALERT_DETAIL: (id: string) => `/api/v1/admin/alerts/${id}`,
  ALERT_ACKNOWLEDGE: (id: string) => `/api/v1/admin/alerts/${id}/acknowledge`,
  ALERT_RESOLVE: (id: string) => `/api/v1/admin/alerts/${id}/resolve`,

  // 租户（仅超级管理员）
  TENANTS: '/api/v1/admin/tenants',
  TENANT_DETAIL: (id: string) => `/api/v1/admin/tenants/${id}`,

  // 管理员用户
  ADMIN_USERS: '/api/v1/admin/users',
  END_USERS: '/api/v1/admin/end-users',
  APP_USERS: '/api/v1/admin/app-users',
  APP_USER_ADJUST_BALANCE: (id: string) => `/api/v1/admin/app-users/${id}/adjust-balance`,
  ALERT_RULES: '/api/v1/admin/alerts/rules',

  // 租户成员
  MEMBERSHIPS: '/api/v1/admin/memberships',
  
  // OCPP 控制
  OCPP_REMOTE_START: '/api/v1/ocpp_control/remote-start-transaction',
  OCPP_REMOTE_STOP: '/api/v1/ocpp_control/remote-stop-transaction',
  OCPP_RESET: '/api/v1/ocpp_control/reset',
  OCPP_CHANGE_CONFIG: '/api/v1/ocpp_control/change-configuration',
  OCPP_GET_CONFIG: '/api/v1/ocpp_control/get-configuration',
  OCPP_UNLOCK: '/api/v1/ocpp_control/unlock-connector',
  
  // 支付管理（Wompi）
  PAYMENTS: '/api/v1/admin/payments',
  PAYMENT_DETAIL: (id: string) => `/api/v1/admin/payments/${id}`,
  PAYMENT_RECONCILE: (id: string) => `/api/v1/admin/payments/${id}/reconcile`,
} as const;

// LocalStorage 键名
export const STORAGE_KEYS = {
  ACCESS_TOKEN: 'access_token',
  REFRESH_TOKEN: 'refresh_token',
  CURRENT_TENANT_ID: 'current_tenant_id',
} as const;

// 刷新间隔（毫秒）
export const REFRESH_INTERVAL = 30000; // 30 秒
export const ACTIVE_SESSION_REFRESH_INTERVAL = 5000; // 活跃会话 5 秒