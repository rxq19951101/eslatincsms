/**
 * 应用配置常量
 */

import Constants from 'expo-constants';

// API基础URL
// 开发环境：使用环境变量或自动检测局域网IP
// 生产环境：使用环境变量配置的生产域名
const inferLanHostFromExpo = (): string | null => {
  // 在真机 Expo Go 下，`localhost` 指向手机自己，必须用电脑局域网 IP
  // 这里尽量兼容不同 Expo/SDK 的字段结构（避免升级/降级导致取不到 host）
  const anyConstants = Constants as unknown as Record<string, any>;

  const hostUri: unknown =
    anyConstants?.expoConfig?.hostUri ??
    anyConstants?.manifest2?.extra?.expoClient?.hostUri ??
    anyConstants?.manifest?.hostUri ??
    anyConstants?.manifest?.debuggerHost ??
    anyConstants?.expoGoConfig?.debuggerHost ??
    anyConstants?.manifest2?.extra?.expoGo?.debuggerHost;

  if (typeof hostUri !== 'string' || !hostUri.trim()) return null;

  // 常见形态：
  // - "192.168.20.124:8081"
  // - "192.168.20.124:19000"
  // - "exp://192.168.20.124:8081"
  // - "192.168.20.124:8081/some/path"
  const cleaned = hostUri
    .trim()
    .replace(/^exp(\+[\w-]+)?:\/\//, '')
    .replace(/^https?:\/\//, '');

  const hostPort = cleaned.split('/')[0] ?? '';
  const host = hostPort.split(':')[0] ?? '';
  if (!host || host === 'localhost' || host === '127.0.0.1') return null;

  return host;
};

const getApiBaseUrl = (): string => {
  // 优先使用环境变量
  if (process.env.EXPO_PUBLIC_API_URL) {
    return process.env.EXPO_PUBLIC_API_URL;
  }
  // 真机（Expo Go / LAN）自动推导电脑 IP：例如 exp://192.168.20.124:8081 -> http://192.168.20.124:9000
  const lanHost = inferLanHostFromExpo();
  if (lanHost) {
    return `http://${lanHost}:9000`;
  }
  // 开发环境默认使用 localhost（适用于模拟器）
  return 'http://localhost:9000';
};

export const API_BASE_URL = getApiBaseUrl();

// 默认租户ID（根据实际情况调整）
export const DEFAULT_TENANT_ID = process.env.EXPO_PUBLIC_TENANT_ID || '0698b167-feaf-423e-a485-d8901b95e3de';

// Token存储键名
export const STORAGE_KEYS = {
  ACCESS_TOKEN: '@eslatin/access_token',
  REFRESH_TOKEN: '@eslatin/refresh_token',
  USER_INFO: '@eslatin/user_info',
  REMEMBER_ME: '@eslatin/remember_me',
  PAYMENT_METHODS: '@eslatin/payment_methods',
} as const;

// API端点
export const API_ENDPOINTS = {
  // 认证相关
  AUTH: {
    REGISTER_EMAIL: '/api/v1/app/auth/register-email',
    LOGIN_EMAIL: '/api/v1/app/auth/login-email',
    VERIFY_EMAIL: '/api/v1/app/auth/verify-email',
    RESET_PASSWORD: '/api/v1/app/auth/reset-password',
    CONFIRM_RESET_PASSWORD: '/api/v1/app/auth/confirm-reset-password',
    RESEND_VERIFICATION: '/api/v1/app/auth/resend-verification',
    SOCIAL_LOGIN: '/api/v1/app/auth/social',
    REFRESH: '/api/v1/app/auth/refresh',
    LOGOUT: '/api/v1/app/auth/logout',
    ME: '/api/v1/app/auth/me',
  },
  // 充电桩相关
  CHARGERS: {
    LIST: '/api/v1/app/chargers',
    DETAIL: (id: string) => `/api/v1/app/chargers/${id}`,
    NEARBY: '/api/v1/app/chargers', // 使用相同的端点，通过参数传递位置
  },
  // 订单相关
  ORDERS: {
    LIST: '/api/v1/orders',
    DETAIL: (id: string) => `/api/v1/orders/${id}`,
    CANCEL: (id: string) => `/api/v1/orders/${id}/cancel`,
  },
  // 充电控制
  CHARGING: {
    // 仅支持扫码充电：走 APP 专用接口（后端会内部调用 OCPP RemoteStart/Stop）
    START: '/api/v1/app/charging/start',
    ACTIVE: '/api/v1/app/charging/active',
    STOP: '/api/v1/app/charging/stop',
    SETTLE: '/api/v1/app/charging/settle',
    METER_VALUES: '/api/v1/app/charging/meter-values',
  },
  // 钱包相关
  WALLET: {
    BALANCE: '/api/v1/app/wallet/balance',
    TOP_UP: '/api/v1/app/wallet/top-up',
    TRANSACTIONS: '/api/v1/app/wallet/transactions',
  },
  // 充电记录（订单记录）
  TRANSACTIONS: {
    LIST: '/api/v1/app/transactions',
    DETAIL: (id: number) => `/api/v1/app/transactions/${id}`,
  },
} as const;

// Deep Link配置
export const DEEP_LINK_CONFIG = {
  SCHEME: 'eslatin',
  PREFIX: 'eslatin://',
  PATHS: {
    VERIFY_EMAIL: 'verify-email',
    RESET_PASSWORD: 'reset-password',
  },
} as const;

// 密码验证规则
export const PASSWORD_RULES = {
  MIN_LENGTH: 8,
  REQUIRE_UPPERCASE: true,
  REQUIRE_LOWERCASE: true,
  REQUIRE_NUMBER: true,
  REQUIRE_SPECIAL: false,
} as const;

// 地图配置
export const MAP_CONFIG = {
  // Mapbox访问令牌（免费账户）
  // 注意：在生产环境中应该使用环境变量
  MAPBOX_ACCESS_TOKEN: process.env.EXPO_PUBLIC_MAPBOX_TOKEN || 'pk.eyJ1IjoiZXNsYXRpbiIsImEiOiJjbTVkZXh5ZTMwMDAwMmxxeG5xaGZpMGVyIn0.placeholder',
  
  // 使用OpenStreetMap样式（免费）
  // 可选：使用Mapbox街道样式 'mapbox://styles/mapbox/streets-v12'
  STYLE_URL: 'https://api.maptiler.com/maps/streets-v2/style.json?key=get_your_own_key',
  
  // 备用：使用Mapbox公开样式（需要token）
  MAPBOX_STYLE_URL: 'mapbox://styles/mapbox/streets-v12',
  
  // 默认位置（哥伦比亚波哥大）
  DEFAULT_ZOOM: 13,
  DEFAULT_LATITUDE: 4.7110,
  DEFAULT_LONGITUDE: -74.0721,
  
  // 搜索和标记配置
  SEARCH_RADIUS: 5000, // 米
  CLUSTER_RADIUS: 50, // 标记聚合半径（像素）
  MAX_ZOOM_LEVEL: 18,
  MIN_ZOOM_LEVEL: 8,
  
  // 标记颜色配置
  MARKER_COLORS: {
    AVAILABLE: '#10B981', // 绿色 - 有空位
    OCCUPIED: '#F59E0B',  // 橙色 - 使用中
    OFFLINE: '#EF4444',   // 红色 - 离线
    UNKNOWN: '#6B7280',   // 灰色 - 未知
  },
} as const;

// 应用主题色
export const COLORS = {
  PRIMARY: '#10B981', // 绿色
  PRIMARY_DARK: '#059669',
  SECONDARY: '#3B82F6', // 蓝色
  SUCCESS: '#10B981',
  WARNING: '#F59E0B',
  ERROR: '#EF4444',
  BACKGROUND: '#F9FAFB',
  CARD_BG: '#FFFFFF',
  TEXT_PRIMARY: '#111827',
  TEXT_SECONDARY: '#6B7280',
  BORDER: '#E5E7EB',
  DISABLED: '#D1D5DB',
} as const;
