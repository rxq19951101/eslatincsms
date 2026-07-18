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

export type SubscriptionPlan = 'free' | 'pro' | 'enterprise';

// 租户管理（超级管理员视角）
export interface TenantRecord {
  id: string;
  name: string;
  domain?: string | null;
  status: string;
  subscription_plan: SubscriptionPlan;
  max_charge_points: number;
  max_users: number;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// 管理员用户（列表/创建等接口的返回）
export interface AdminUserRecord {
  id: string;
  username: string;
  email: string;
  full_name?: string | null;
  is_active: boolean;
  is_super_admin: boolean;
  last_login_at?: string | null;
  created_at: string;
  updated_at: string;
}

// 租户成员关系
export interface MembershipRecord {
  id: string;
  tenant_id: string;
  tenant_name: string;
  admin_user_id: string;
  admin_username: string;
  is_primary: boolean;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface TenantProvisionResponse {
  tenant: TenantRecord;
  admin: AdminUserRecord;
  membership_id: string;
}

export interface TenantProvisionResult extends TenantProvisionResponse {
  temporary_password: string;
}

export interface TenantProvisionRequest {
  tenant: {
    name: string;
    domain: string | null;
    subscription_plan: SubscriptionPlan;
    max_charge_points: number;
    max_users: number;
    settings: Record<string, unknown>;
  };
  admin: {
    username: string;
    email: string;
    password: string;
    full_name: string | null;
  };
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
    default_tenant_id?: string; // 登录响应中包含默认租户 ID
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

export interface DashboardSiteItem {
  site_id: string;
  site_name: string;
  address?: string | null;

  charge_points_count: number;
  online_charge_points_count: number;

  faulted_charge_points: number;
  charging_charge_points: number;
  available_charge_points: number;

  orders_count: number;
  energy_kwh: number;
  revenue: number;
}

// 充电桩相关类型
export interface ChargePoint {
  id: string; // Internal database UUID; never use as the OCPP command identity.
  ocpp_identity: string; // External charger identity used by OCPP commands and UI.
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

// 站点管理类型（Admin Web）
export interface SiteListItem {
  id: string;
  site_code: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  is_active: boolean;
  operating_hours?: string | null;
  domain?: string | null;
  charge_points_count: number;
  online_charge_points_count: number;
  created_at: string;
  updated_at: string;
}

export interface SiteDetailChargePoint {
  id: string; // Internal database UUID.
  ocpp_identity?: string; // External charger identity safe for operator display.
  vendor?: string | null;
  model?: string | null;
  status: string;
  last_seen?: string | null;
  site_id: string;
  site_name?: string | null;
}

export interface SiteDetail {
  id: string;
  site_code: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  is_active: boolean;
  operating_hours?: string | null;
  domain?: string | null;
  price_per_kwh?: number | null;
  charge_points: SiteDetailChargePoint[];
  created_at: string;
  updated_at: string;
}

export interface BindChargePointsRequest {
  charge_point_ids: string[];
  force_move?: boolean;
}

export interface CreateChargePointInSiteRequest {
  id: string; // 兼容 API 字段；语义为 ocpp_identity
  vendor?: string;
  model?: string;
  connector_count?: number;
  connector_type?: string;
}

// 交易相关类型
export interface Transaction {
  id: string;
  transaction_id: string | number;
  charge_point_id: string; // Internal ChargePoint UUID used for database relations.
  ocpp_identity?: string; // External identity, when included by the API, for display only.
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
  id: string; // Internal alert UUID.
  alert_type: string;
  severity: 'critical' | 'warning' | 'info';
  charge_point_id?: string; // Internal ChargePoint UUID used for API relations.
  ocpp_identity?: string; // External charger identity safe for operator display.
  evse_id?: number;
  title: string;
  description: string;
  status: 'pending' | 'acknowledged' | 'resolved';
  tenant_id: string;
  metadata: Record<string, unknown>;
  acknowledged_by?: string;
  acknowledged_at?: string;
  resolved_at?: string;
  created_at: string;
  updated_at: string;
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
