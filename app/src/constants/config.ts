/**
 * 应用配置常量
 */

import Constants from 'expo-constants';
import { Platform } from 'react-native';

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

const isProductionBuild = !__DEV__;

const getApiBaseUrl = (): string => {
  const fromEnv = process.env.EXPO_PUBLIC_API_URL?.trim();
  if (fromEnv) {
    if (isProductionBuild && !fromEnv.startsWith('https://')) {
      console.error(
        '[Config] Production builds require EXPO_PUBLIC_API_URL with HTTPS (App Transport Security).'
      );
    }
    return fromEnv.replace(/\/$/, '');
  }

  if (isProductionBuild) {
    console.error(
      '[Config] EXPO_PUBLIC_API_URL is required for production builds. Set it in EAS secrets or .env.'
    );
    return 'https://api.eslatin.com.co';
  }

  // Web：按浏览器当前访问的主机推导 CSMS，避免沿用 Expo manifest 里的 LAN IP（本机 Chrome 常开 localhost:8081，API 误指向 192.168.* 会连不上）
  if (Platform.OS === 'web') {
    if (typeof window !== 'undefined' && window.location?.hostname) {
      const hostname = window.location.hostname;
      if (hostname === 'localhost' || hostname === '127.0.0.1') {
        return 'http://localhost:9000';
      }
      return `http://${hostname}:9000`;
    }
    return 'http://localhost:9000';
  }

  const lanHost = inferLanHostFromExpo();
  if (lanHost) {
    return `http://${lanHost}:9000`;
  }
  return 'http://localhost:9000';
};

export const API_BASE_URL = getApiBaseUrl();

const extra = Constants.expoConfig?.extra as Record<string, string | undefined> | undefined;

export const LEGAL_URLS = {
  privacy:
    process.env.EXPO_PUBLIC_PRIVACY_POLICY_URL?.trim() ||
    extra?.privacyPolicyUrl ||
    `${API_BASE_URL}/legal/privacy.html`,
  terms:
    process.env.EXPO_PUBLIC_TERMS_URL?.trim() ||
    extra?.termsOfServiceUrl ||
    `${API_BASE_URL}/legal/terms.html`,
  supportEmail: extra?.supportEmail || 'support@eslatin.com.co',
} as const;

/** 应用内三方支付轨；默认关闭，上架后接 Wompi/MP 时设为 true */
export const PAYMENT_RAILS_ENABLED =
  (process.env.EXPO_PUBLIC_PAYMENT_RAILS_ENABLED || 'false').toLowerCase() === 'true';

export const MIN_BALANCE_COP = Number(process.env.EXPO_PUBLIC_MIN_BALANCE_COP || 5000);

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
  SITES: {
    LIST: '/api/v1/app/sites',
    DETAIL: (id: string) => `/api/v1/app/sites/${id}`,
  },
  FAVORITES: {
    LIST: '/api/v1/app/favorites',
    DETAIL: (siteId: string) => `/api/v1/app/favorites/${siteId}`,
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
    CHECK: '/api/v1/app/charging/check',
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
    UNPAID_CHARGES: '/api/v1/app/wallet/unpaid-charges',
    PAY_UNPAID_CHARGE: '/api/v1/app/wallet/pay-unpaid-charge',
    // Legacy endpoint kept only for unregistered code paths; active App code
    // uses /api/v1/app/payment-methods.
    SAVED_PAYMENT_METHODS: '/api/v1/app/wallet/saved-payment-methods',
  },
  // 支付相关
  PAYMENTS: {
    // Legacy endpoints are not registered in the current App API. New flows
    // must use /api/v1/app/payments/checkout-sessions.
    CREATE: '/api/v1/app/wallet/payments/create',
    CREATE_MP: '/api/v1/app/wallet/payments/create-mp',
    STATUS: (orderId: string) => `/api/v1/app/wallet/payments/${orderId}/status`,
  },
  // 充电记录（订单记录）
  TRANSACTIONS: {
    LIST: '/api/v1/app/transactions',
    DETAIL: (id: string) => `/api/v1/app/transactions/${id}`,
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
  PRIMARY: '#0876BE',
  PRIMARY_DARK: '#07598F',
  PRIMARY_SOFT: '#E7F7FC',
  SECONDARY: '#22C7D4',
  SUCCESS: '#0F956B',
  WARNING: '#B86500',
  ERROR: '#C92A2A',
  BACKGROUND: '#F5FAFD',
  CARD_BG: '#FFFFFF',
  TEXT_PRIMARY: '#102A43',
  TEXT_SECONDARY: '#5B7083',
  TEXT_TERTIARY: '#8799A8',
  BORDER: '#D8E7F0',
  DISABLED: '#B8C8D3',
  // iOS 风格颜色
  // 注意：IOS_BLUE 曾是 iOS 系统蓝，历史上与品牌绿色 PRIMARY 混用导致全局配色不一致。
  // 统一为品牌主色，使 Button/TabBar 等系统级交互色与各页面自绘按钮保持一致。
  IOS_BLUE: '#0876BE',
  IOS_GRAY: '#6F8292',
  IOS_LIGHT_GRAY: '#EEF6FA',
  IOS_SEPARATOR: '#D8E7F0',
  IOS_WHITE: '#FFFFFF',
  IOS_BLACK: '#000000',
} as const;

// iOS 风格样式常量
export const IOS_STYLES = {
  // 圆角
  RADIUS: {
    SMALL: 8,
    MEDIUM: 12,
    LARGE: 16,
    XLARGE: 20,
    ROUND: 9999,
  },
  // 间距（8px 基准）
  SPACING: {
    XS: 4,
    SM: 8,
    MD: 16,
    LG: 24,
    XL: 32,
    XXL: 48,
  },
  // 阴影（iOS 风格）
  SHADOW: {
    SMALL: {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 1 },
      shadowOpacity: 0.04,
      shadowRadius: 2,
      elevation: 1,
    },
    MEDIUM: {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.07,
      shadowRadius: 6,
      elevation: 2,
    },
    LARGE: {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: 0.16,
      shadowRadius: 16,
      elevation: 8,
    },
  },
  // 字体大小
  FONT_SIZE: {
    TINY: 10,
    SMALL: 12,
    BODY: 14,
    MEDIUM: 16,
    LARGE: 18,
    XLARGE: 20,
    TITLE: 24,
    HEADLINE: 28,
  },
  // 字体权重
  FONT_WEIGHT: {
    REGULAR: '400' as const,
    MEDIUM: '500' as const,
    SEMIBOLD: '600' as const,
    BOLD: '700' as const,
    HEAVY: '800' as const,
  },
  // Wompi 支付配置（保留兼容）
  WOMPI: {
    PUBLIC_KEY_SANDBOX: process.env.EXPO_PUBLIC_WOMPI_PUBLIC_KEY_SANDBOX || '',
    PUBLIC_KEY_PROD: process.env.EXPO_PUBLIC_WOMPI_PUBLIC_KEY_PROD || '',
    CHECKOUT_URL: process.env.EXPO_PUBLIC_WOMPI_CHECKOUT_URL || 'https://checkout.wompi.co/l',
    ENVIRONMENT: process.env.EXPO_PUBLIC_WOMPI_ENVIRONMENT || 'sandbox',
  },
} as const;
