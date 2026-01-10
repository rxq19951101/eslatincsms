// 用户相关类型
export interface AdminUser {
  id: string;
  username: string;
  email: string;
  full_name?: string;
  is_super_admin: boolean;
  default_tenant_id?: string;
  tenant_list: Tenant[];
}

export interface Tenant {
  id: string;
  name: string;
  is_primary: boolean;
}

// 认证相关类型
export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: {
    id: string;
    username: string;
    email: string;
    full_name?: string;
    is_super_admin: boolean;
  };
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface RefreshTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

// Dashboard 相关类型
export interface DashboardSummary {
  total_charge_points: number;
  online_charge_points: number;
  offline_charge_points: number;
  faulted_charge_points: number;
  charging_charge_points: number;
  available_charge_points: number;
  total_sites: number;
  active_sites: number;
  today_orders: number;
  today_energy_kwh: number;
  today_revenue: number;
  total_users: number;
  active_users_today: number;
  critical_alerts: number;
  warning_alerts: number;
  info_alerts: number;
}

export interface TrendDataPoint {
  date: string;
  value: number;
}

export interface DashboardTrends {
  energy_trend: TrendDataPoint[];
  revenue_trend: TrendDataPoint[];
  orders_trend: TrendDataPoint[];
}

// 充电桩相关类型
export interface ChargePoint {
  id: string;
  vendor?: string;
  model?: string;
  status: string;
  last_seen?: string;
  location?: {
    latitude?: number;
    longitude?: number;
    address?: string;
  };
  price_per_kwh?: number;
  is_configured: boolean;
  has_location: boolean;
  has_pricing: boolean;
}

export interface ChargePointDetail extends ChargePoint {
  serial_number?: string;
  firmware_version?: string;
  connector_type?: string;
  evses?: EVSE[];
  created_at?: string;
  updated_at?: string;
}

export interface EVSE {
  evse_id: number;
  connector_type: string;
  max_power_kw?: number;
  status: string;
  last_seen?: string;
}

// 交易相关类型
export interface Transaction {
  id: string;
  transaction_id: string;
  charge_point_id: string;
  id_tag: string;
  user_id?: string;
  start_time: string;
  end_time?: string;
  energy_kwh?: number;
  duration_minutes?: number;
  status: string;
}

// 告警相关类型
export interface Alert {
  id: string;
  type: string;
  severity: 'critical' | 'warning' | 'info';
  charge_point_id?: string;
  description: string;
  status: 'pending' | 'acknowledged' | 'resolved';
  created_at: string;
  updated_at?: string;
}

// API 错误类型
export interface ApiError {
  detail: string;
  status_code: number;
}

// 分页类型
export interface PaginationParams {
  limit?: number;
  offset?: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}