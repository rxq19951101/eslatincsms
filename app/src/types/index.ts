/**
 * 全局TypeScript类型定义
 */

// ==================== 用户相关 ====================

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone?: string;
  email_verified: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LoginResponse extends AuthTokens {
  user: User;
}

// ==================== 充电桩相关 ====================

export interface Location {
  latitude: number;
  longitude: number;
  address: string;
}

export interface EVSE {
  evse_id: number;
  connector_type: string;
  max_power_kw: number;
  status: 'Available' | 'Charging' | 'Offline' | 'Faulted';
  last_seen?: string;
}

export interface ChargePoint {
  id: string;
  vendor: string;
  model: string;
  status: 'Available' | 'Charging' | 'Offline' | 'Faulted';
  location: Location;
  price_per_kwh: number;
  site_name?: string;
  rating?: number;
  reviews_count?: number;
  distance?: number; // 距离（米）
  evses: EVSE[];
  last_seen?: string;
}

// ==================== 订单/预订相关 ====================

export interface Order {
  id: string;
  charge_point_id: string;
  charge_point: ChargePoint;
  booking_date: string;
  arrival_time: string;
  charging_duration: number; // 分钟
  amount_estimation: number;
  tax: number;
  total_amount: number;
  payment_method: string;
  status: 'upcoming' | 'completed' | 'cancelled';
  created_at: string;
}

export interface ChargingSession {
  id: string;
  order_id: string;
  energy_kwh: number;
  duration_seconds: number;
  battery_percent: number;
  current_amp: number;
  cost: number;
  status: 'charging' | 'completed' | 'stopped';
}

// ==================== 钱包相关 ====================

export interface WalletBalance {
  balance: number;
  currency: string;
}

export interface WalletTransaction {
  id: string;
  type: 'charge' | 'top_up';
  amount: number;
  description: string;
  created_at: string;
  charge_point_name?: string;
}

export interface PaymentMethod {
  id: string;
  type: 'paypal' | 'google_pay' | 'apple_pay' | 'visa' | 'mastercard';
  last_four?: string;
  is_default: boolean;
}

// ==================== 导航相关 ====================

export type RootStackParamList = {
  // Auth
  Welcome: undefined;
  EmailLogin: undefined;
  EmailRegister: undefined;
  EmailVerification: { email: string };
  VerificationSuccess: undefined;
  ForgotPassword: undefined;
  ResetPassword: { token: string };
  SocialAuthCallback: { provider: string; token: string };
  
  // Main App
  MainTabs: undefined;
  LocationPermission: undefined;
  StationDetail: { chargePointId: string };
  // 仅支持扫码充电：不再实现预订模块（BookingDetail 等路由移除）
  ChargingProcess: { qrToken: string };
  ChargingComplete: { chargePointId?: string };
  ChargingHistory: undefined;
  ChargingHistoryDetail: { id: number };
  TopUp: undefined;
  PaymentMethod: undefined;
  TransactionHistory: undefined;
  PaymentMethods: undefined;
  AddPayment: undefined;
  PersonalInfo: undefined;
  Security: undefined;
  Language: undefined;
  HelpCenter: undefined;
  PrivacyPolicy: undefined;
  About: undefined;
};

export type MainTabsParamList = {
  Home: undefined;
  Saved: undefined;
  Scan: undefined;
  MyWallet: undefined;
  Account: undefined;
};

// ==================== API请求/响应类型 ====================

export interface ApiError {
  message: string;
  code?: string;
  details?: any;
}

export interface PaginationParams {
  page?: number;
  page_size?: number;
}

export interface PaginationResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
