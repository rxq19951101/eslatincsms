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
  id: string;
  connector_id: number;
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

/** PAY-MP-001 canonical payment-method projection. */
export type CanonicalPaymentMethodType = 'credit_card' | 'debit_card' | 'prepaid_card';

export interface CanonicalPaymentMethod {
  id: string;
  provider: string;
  brand?: string | null;
  payment_type?: CanonicalPaymentMethodType | null;
  last_four?: string | null;
  is_default: boolean;
}

export interface CanonicalPaymentMethodsResponse {
  items: CanonicalPaymentMethod[];
}

export interface SaveCardCheckoutSessionRequest {
  purpose: 'save_card';
  payment_method_mode: 'new_card';
  save_card: true;
  currency: 'COP';
  return_url: string;
  idempotency_key: string;
}

export interface SaveCardCheckoutSessionResponse {
  checkout_session_id: string;
  checkout_url: string;
  expires_at: string;
  purpose: 'save_card';
}

export type PaymentCheckoutPurpose =
  | 'save_card'
  | 'wallet_top_up'
  | 'charging_direct'
  | 'unpaid_charge';

export type PaymentCheckoutStatus =
  | 'created'
  | 'ready'
  | 'processing'
  | 'action_required'
  | 'approved'
  | 'declined'
  | 'expired'
  | 'error';

export interface CheckoutSessionNextAction {
  type: 'open_url';
  url: string;
}

export interface CheckoutSessionResponse {
  id: string;
  purpose: PaymentCheckoutPurpose;
  status: PaymentCheckoutStatus;
  payment_intent_id?: string | null;
  payment_order_id?: string | null;
  saved_payment_method_id?: string | null;
  next_action?: CheckoutSessionNextAction | null;
  expires_at: string;
}

export interface CreateCheckoutSessionRequest {
  purpose: PaymentCheckoutPurpose;
  payment_method_mode: 'new_card' | 'saved_card';
  saved_payment_method_id?: string | null;
  save_card: boolean;
  amount?: string;
  currency?: 'COP';
  charge_point_id?: string | null;
  connector_id?: number | null;
  session_id?: string | null;
  return_url: string;
  idempotency_key: string;
}

export interface CreateCheckoutSessionResponse {
  checkout_session_id: string;
  checkout_url: string;
  expires_at: string;
  purpose: PaymentCheckoutPurpose;
}

export interface WalletTransaction {
  id: string;
  type: 'charge' | 'top_up' | 'refund' | 'adjustment' | string;
  amount: number;
  reference?: string | null;
  description?: string | null;
  created_at: string;
  charge_point_name?: string | null;
  ocpp_identity?: string | null;
  charging_session_id?: string | null;
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
    session_id?: string;
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
  session_id: string;
  charge_point_id: string;
  ocpp_identity?: string | null;
  charge_point_name?: string | null;
  amount: number;
  currency: string;
  created_at: string;
  payment_order_id?: string;
}

/** 支付通道（预留：PSE / 本地钱包等） */
export type PaymentRail = 'card' | 'wallet' | 'pse' | 'nequi' | 'daviplata' | 'other';

// ==================== 导航相关 ====================

import type { NavigatorScreenParams } from '@react-navigation/native';

export type PaymentReturnStatus =
  | 'created'
  | 'ready'
  | 'processing'
  | 'action_required'
  | 'approved'
  | 'declined'
  | 'expired'
  | 'error';

export type PaymentResultStatus = PaymentReturnStatus | 'voided' | 'refunded';

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
  StationDetail: { siteId: string };
  // 仅支持扫码充电：不再实现预订模块（BookingDetail 等路由移除）
  ChargingProcess: { qrToken?: string; sessionId?: string };
  ChargingComplete: { ocppIdentity?: string };
  ChargingHistory: undefined;
  ChargingHistoryDetail: { id: string };
  TopUp: undefined;
  PaymentMethod: undefined;
  TransactionHistory: undefined;
  PaymentMethods: undefined;
  /** 支付中枢：余额 + 充值 + 支付方式（演示） */
  PaymentHub: undefined;
  AddPayment: undefined;
  WompiPayment: { orderId?: string; checkoutUrl?: string; amount?: number };
  MercadoPagoPayment: { amount: number; type: 'top_up' | 'charging'; metadata?: { session_id?: string; charge_point_id?: string; site_id?: string } };
  PaymentResult: {
    orderId?: string;
    status?: PaymentResultStatus;
    checkout_session_id?: string;
  };
  UnpaidBills: undefined;
  UnpaidBillDetail: { invoiceId: string };
  SupportCases: undefined;
  SupportCaseDetail: { caseId: string };
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
  status?: number;
  details?: any;
  fieldErrors?: Record<string, string>;
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
