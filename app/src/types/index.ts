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

export interface SavedPaymentMethodItem {
  id: string;
  provider: string;
  last_four?: string;
  payment_method_brand?: string;
  is_default: boolean;
}

export interface SavedPaymentMethodsResponse {
  items: SavedPaymentMethodItem[];
  hint: string;
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

// ==================== 支付相关 =====================

// Wompi 相关（保留兼容）
export interface WompiPaymentData {
  public_key: string;
  reference: string;
  integrity_signature: string;
  amount_in_cents: number;
  currency: string;
  redirect_url: string;
}

export interface CreatePaymentRequest {
  type: 'top_up' | 'charging';
  amount: number;
  currency?: string;
  metadata?: {
    session_id?: number;
    charge_point_id?: string;
    site_id?: string;
  };
}

export interface CreatePaymentResponse {
  order_id: string;
  reference: string;
  payment_data: WompiPaymentData;
  checkout_url?: string;
}

export type PaymentProviderCode = 'wompi' | 'mercadopago';

export interface PaymentProviderOption {
  code: PaymentProviderCode;
  name: string;
  description: string;
  enabled: boolean;
  supportedTypes: Array<'top_up' | 'charging'>;
}

// Mercado Pago 相关
export interface CardData {
  number: string;
  expMonth: string;
  expYear: string;
  cvc: string;
  holderName: string;
}

/** MP card_tokens 解析结果（优先用接口返回的 payment_method_id，避免仅凭卡号首位误判） */
export interface MercadoPagoCardTokenResult {
  tokenId: string;
  payment_method_id: string;
}

export interface CreateMercadoPagoPaymentRequest {
  type: 'top_up' | 'charging';
  amount: number;
  currency?: string;
  token: string;  // 前端获取的 card token
  email: string;  // MP 强制要求
  payment_method_id: string;  // 'visa', 'master' 等
  idempotency_key: string;  // UUID v4
  device_id?: string;  // 设备指纹（可选）
  description?: string;  // 支付描述（可选）
  metadata?: {
    session_id?: number;
    charge_point_id?: string;
    site_id?: string;
  };
}

export interface MercadoPagoPaymentResponse {
  order_id: string;
  payment_id: string;
  status: string;
  external_reference: string;
  amount: number;
  currency: string;
}

export interface PaymentStatusResponse {
  order_id: string;
  status: 'created' | 'processing' | 'approved' | 'declined' | 'voided' | 'error' | 'expired' | 'refunded';
  wompi_transaction_id?: string;
  mercadopago_payment_id?: string;
  amount: number;
  currency: string;
  paid_at?: string;
  expires_at: string;
  is_expired: boolean;
}

export interface UnpaidCharge {
  session_id: number;
  charge_point_id: string;
  amount: number;
  currency: string;
  created_at: string;
  payment_order_id?: string;
}

/** 支付通道（预留：PSE / 本地钱包等） */
export type PaymentRail = 'card' | 'wallet' | 'pse' | 'nequi' | 'daviplata' | 'other';

// ==================== 导航相关 ====================

import type { NavigatorScreenParams } from '@react-navigation/native';

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
  MainTabs: NavigatorScreenParams<MainTabsParamList> | undefined;
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
  /** 支付中枢：余额 + 充值 + 支付方式（演示） */
  PaymentHub: undefined;
  AddPayment: undefined;
  WompiPayment: { orderId?: string; checkoutUrl?: string; amount?: number };
  MercadoPagoPayment: { amount: number; type: 'top_up' | 'charging'; metadata?: { session_id?: number; charge_point_id?: string; site_id?: string } };
  PaymentResult: { orderId?: string; status?: string };
  UnpaidBills: undefined;
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
