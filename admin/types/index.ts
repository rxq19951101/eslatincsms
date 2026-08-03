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
  commissioning_status?: 'draft' | 'testing' | 'ready' | 'commissioned' | 'suspended';
  acceptance_report?: AcceptanceReport | null;
  last_acceptance_at?: string | null;
  commissioned_at?: string | null;
  lifecycle_status?: 'active' | 'retired';
  retirement_reason?: string | null;
  retirement_requested_at?: string | null;
  retired_at?: string | null;
  original_site?: {
    id: string;
    site_code: string;
    name: string;
  } | null;
}

export interface AcceptanceReport {
  version: number;
  generated_at: string;
  ocpp_identity: string;
  protocol: string;
  passed: boolean;
  checks: Record<string, boolean>;
  evidence_counts: Record<string, number>;
}

export interface EVSE {
  evse_id: number;
  physical_reference?: string;
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
  lifecycle_status?: 'active' | 'archived';
  archived_at?: string | null;
  archive_reason?: string | null;
  active_charge_points_count?: number;
  retiring_charge_points_count?: number;
  retired_charge_points_count?: number;
  created_at: string;
  updated_at: string;
}

export interface SiteDetailChargePoint {
  id: string; // Internal database UUID.
  ocpp_identity?: string; // External charger identity safe for operator display.
  display_code: string;
  display_name?: string | null;
  location_hint?: string | null;
  vendor?: string | null;
  model?: string | null;
  status: string;
  last_seen?: string | null;
  site_id: string;
  site_name?: string | null;
  lifecycle_status?: 'active' | 'retired';
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
  lifecycle_status?: 'active' | 'archived';
  archived_at?: string | null;
  archive_reason?: string | null;
  active_charge_points_count?: number;
  retiring_charge_points_count?: number;
  retired_charge_points_count?: number;
  created_at: string;
  updated_at: string;
}

export interface AssetArchiveActor {
  id: string;
  username?: string | null;
  full_name?: string | null;
}

export interface ArchivedSiteItem {
  id: string;
  site_code: string;
  name: string;
  address: string;
  lifecycle_status: 'archived';
  archived_at?: string | null;
  archive_reason?: string | null;
  archived_by?: AssetArchiveActor | null;
  active_charge_points_count: number;
  retiring_charge_points_count: number;
  retired_charge_points_count: number;
}

export interface RetiredChargerItem {
  id: string;
  ocpp_identity: string;
  display_code: string;
  display_name?: string | null;
  vendor?: string | null;
  model?: string | null;
  lifecycle_status: 'retired';
  retirement_reason?: string | null;
  retired_at?: string | null;
  retired_by?: AssetArchiveActor | null;
  original_site: {
    id: string;
    site_code: string;
    name: string;
  };
}

export interface BindChargePointsRequest {
  charge_point_ids: string[];
  force_move?: boolean;
}

export interface CreateChargePointInSiteRequest {
  id: string; // 兼容 API 字段；语义为 ocpp_identity
  display_code: string;
  display_name?: string;
  location_hint?: string;
  vendor?: string;
  model?: string;
  connector_count?: number;
  connector_type?: string;
  evses?: Array<{
    evse_id: number;
    physical_reference: string;
    connector_type: string;
    max_power_kw: number;
  }>;
}

// 交易相关类型
export interface ActiveSession {
  id: string;
  user_reference?: string | null;
  start_time?: string | null;
  energy_kwh?: number | null;
  power_kw?: number | null;
  duration_minutes?: number | null;
  estimated_cost?: string | null;
  currency?: string | null;
  last_meter_at?: string | null;
  status: string;
  site?: {
    id?: string;
    site_code?: string | null;
    name?: string | null;
    address?: string | null;
  } | null;
  charger?: {
    id: string;
    display_code?: string | null;
    display_name?: string | null;
  } | null;
  connector?: {
    id: string;
    connector_number: number;
    physical_reference?: string | null;
  } | null;
}

export interface ChargingRecord {
  id: string;
  record_number: string | null;
  invoice_number: string | null;
  ocpp_transaction_id: string | number | null;
  site: {
    site_code: string | null;
    name: string | null;
    address: string | null;
  } | null;
  charger: {
    display_code: string | null;
    display_name: string | null;
    ocpp_identity: string | null;
  } | null;
  connector: {
    evse_id: number | null;
    physical_reference: string | null;
    connector_type: string | null;
    max_power_kw: string | null;
  } | null;
  user_reference: string | null;
  start_time: string | null;
  end_time: string | null;
  energy_kwh: string | null;
  duration_minutes: string | null;
  amount: string | null;
  currency: string | null;
  status: string;
  payment_status: string | null;
  anomaly_codes: TransactionAnomalyCode[];
}

export type TransactionAnomalyCode =
  | 'invalid_meter_delta'
  | 'missing_end_time'
  | 'power_exceeds_rating';

// 告警相关类型
export interface Alert {
  id: string; // Internal alert UUID.
  alert_type: string;
  severity: 'critical' | 'warning' | 'info';
  charge_point_id?: string | null; // Internal ChargePoint UUID used for API relations; never display.
  ocpp_identity?: string; // External charger identity safe for operator display.
  evse_id?: string | null; // Internal EVSE UUID used for API relations; never display.
  title: string;
  description?: string | null;
  status: 'pending' | 'acknowledged' | 'resolved';
  tenant_id: string;
  metadata: Record<string, unknown>;
  alert_code?: string | null;
  message_params?: Record<string, unknown> | null;
  raw_message?: string | null;
  site?: {
    site_code?: string | null;
    name?: string | null;
    address?: string | null;
  } | null;
  charge_point?: {
    ocpp_identity?: string | null;
    model?: string | null;
    serial_number?: string | null;
  } | null;
  evse?: {
    evse_id?: number | null;
    physical_reference?: string | null;
  } | null;
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
