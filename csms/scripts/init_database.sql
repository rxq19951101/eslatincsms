-- ============================================
-- 多租户充电桩运营平台数据库初始化脚本
-- ============================================

-- 1. 创建扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. 创建数据库角色（用于 RLS 绕过）
CREATE ROLE IF NOT EXISTS app_user;
CREATE ROLE IF NOT EXISTS app_super;
ALTER ROLE app_super BYPASSRLS;

-- 3. 创建所有表（按依赖顺序）

-- ==================== 3.1 租户表 ====================
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    domain VARCHAR(200) UNIQUE,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    subscription_plan VARCHAR(50) NOT NULL DEFAULT 'free',
    max_charge_points INTEGER DEFAULT 10,
    max_users INTEGER DEFAULT 100,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenants_domain ON tenants(domain);
CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);

-- ==================== 3.2 用户表 ====================

-- AdminUser（管理员用户表）
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(200) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(200),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_super_admin BOOLEAN NOT NULL DEFAULT FALSE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users(email);
CREATE INDEX IF NOT EXISTS idx_admin_users_username ON admin_users(username);

-- EndUser（终端用户表）
CREATE TABLE IF NOT EXISTS end_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    phone VARCHAR(50) NOT NULL,
    email VARCHAR(200),
    full_name VARCHAR(200),
    id_tag VARCHAR(100) NOT NULL,
    balance NUMERIC(10, 2) NOT NULL DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, phone),
    UNIQUE(tenant_id, id_tag),
    UNIQUE(tenant_id, email) WHERE email IS NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_end_users_tenant_id ON end_users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_end_users_phone ON end_users(phone);
CREATE INDEX IF NOT EXISTS idx_end_users_id_tag ON end_users(id_tag);

-- TenantMembership（租户成员关系表）
CREATE TABLE IF NOT EXISTS tenant_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    admin_user_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, admin_user_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_memberships_tenant_id ON tenant_memberships(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_memberships_admin_user_id ON tenant_memberships(admin_user_id);
CREATE INDEX IF NOT EXISTS idx_tenant_memberships_primary ON tenant_memberships(admin_user_id, is_primary) WHERE is_primary = TRUE;

-- Role（角色表）
CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    permissions JSONB NOT NULL DEFAULT '[]',
    description TEXT,
    scope VARCHAR(50) NOT NULL DEFAULT 'tenant',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, name)
);

CREATE INDEX IF NOT EXISTS idx_roles_tenant_id ON roles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_roles_scope ON roles(scope);

-- TenantMembershipRole（成员角色关系表）
CREATE TABLE IF NOT EXISTS tenant_membership_roles (
    membership_id UUID NOT NULL REFERENCES tenant_memberships(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (membership_id, role_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_membership_roles_membership_id ON tenant_membership_roles(membership_id);
CREATE INDEX IF NOT EXISTS idx_tenant_membership_roles_role_id ON tenant_membership_roles(role_id);

-- ==================== 3.3 告警监控表 ====================

-- Alert（告警表）
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    charge_point_id VARCHAR(100) REFERENCES charge_points(id) ON DELETE SET NULL,
    evse_id INTEGER REFERENCES evses(id) ON DELETE SET NULL,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    title VARCHAR(200) NOT NULL,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    acknowledged_by UUID REFERENCES admin_users(id),
    acknowledged_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_tenant_id ON alerts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_alerts_charge_point_id ON alerts(charge_point_id);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at);

-- AlertRule（告警规则表）
CREATE TABLE IF NOT EXISTS alert_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    conditions JSONB NOT NULL,
    severity VARCHAR(50) NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, name)
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_tenant_id ON alert_rules(tenant_id);
CREATE INDEX IF NOT EXISTS idx_alert_rules_is_enabled ON alert_rules(is_enabled);

-- ==================== 3.4 系统配置表 ====================

-- SystemConfig（系统配置表）
CREATE TABLE IF NOT EXISTS system_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    config_key VARCHAR(200) NOT NULL,
    config_value TEXT,
    value_type VARCHAR(20) NOT NULL DEFAULT 'string',
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, config_key)
);

CREATE INDEX IF NOT EXISTS idx_system_configs_tenant_id_key ON system_configs(tenant_id, config_key);

-- ==================== 3.5 Token 管理表 ====================

-- RefreshToken（刷新Token表）
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jti VARCHAR(100) NOT NULL UNIQUE,
    user_id UUID NOT NULL,
    user_type VARCHAR(20) NOT NULL,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    device_info JSONB,
    ip_address VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_jti ON refresh_tokens(jti);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id, user_type);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);

-- ==================== 3.6 审计日志表 ====================

-- AuditLog（审计日志表）
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    actor_id UUID NOT NULL,
    actor_type VARCHAR(20) NOT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(100),
    before_data JSONB,
    after_data JSONB,
    ip_address VARCHAR(50),
    user_agent TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_id ON audit_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor_id, actor_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- ==================== 4. 为现有业务表添加 tenant_id 字段 ====================

-- 注意：这些表可能已经存在，使用 IF NOT EXISTS 或 ALTER TABLE ADD COLUMN IF NOT EXISTS
-- 由于 PostgreSQL 不支持 IF NOT EXISTS for ALTER TABLE ADD COLUMN，我们需要先检查

-- Sites 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='sites' AND column_name='tenant_id') THEN
        ALTER TABLE sites ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_sites_tenant_id ON sites(tenant_id);
    END IF;
END $$;

-- ChargePoints 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='charge_points' AND column_name='tenant_id') THEN
        ALTER TABLE charge_points ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_charge_points_tenant_id ON charge_points(tenant_id);
    END IF;
END $$;

-- Devices 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='devices' AND column_name='tenant_id') THEN
        ALTER TABLE devices ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_devices_tenant_id ON devices(tenant_id);
    END IF;
END $$;

-- Orders 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='tenant_id') THEN
        ALTER TABLE orders ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_orders_tenant_id ON orders(tenant_id);
    END IF;
END $$;

-- Invoices 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='invoices' AND column_name='tenant_id') THEN
        ALTER TABLE invoices ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_invoices_tenant_id ON invoices(tenant_id);
    END IF;
END $$;

-- ChargingSessions 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='charging_sessions' AND column_name='tenant_id') THEN
        ALTER TABLE charging_sessions ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_charging_sessions_tenant_id ON charging_sessions(tenant_id);
    END IF;
END $$;

-- Tariffs 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tariffs' AND column_name='tenant_id') THEN
        ALTER TABLE tariffs ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_tariffs_tenant_id ON tariffs(tenant_id);
    END IF;
END $$;

-- SupportMessages 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='support_messages' AND column_name='tenant_id') THEN
        ALTER TABLE support_messages ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_support_messages_tenant_id ON support_messages(tenant_id);
    END IF;
END $$;

-- EVSEs 表（通过 charge_points 关联，但也可以直接添加）
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='evses' AND column_name='tenant_id') THEN
        ALTER TABLE evses ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_evses_tenant_id ON evses(tenant_id);
    END IF;
END $$;

-- EVSEStatus 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='evse_status' AND column_name='tenant_id') THEN
        ALTER TABLE evse_status ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_evse_status_tenant_id ON evse_status(tenant_id);
    END IF;
END $$;

-- MeterValues 表（通过 charging_sessions 关联）
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='meter_values' AND column_name='tenant_id') THEN
        ALTER TABLE meter_values ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_meter_values_tenant_id ON meter_values(tenant_id);
    END IF;
END $$;

-- PricingSnapshots 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='pricing_snapshots' AND column_name='tenant_id') THEN
        ALTER TABLE pricing_snapshots ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_pricing_snapshots_tenant_id ON pricing_snapshots(tenant_id);
    END IF;
END $$;

-- Payments 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payments' AND column_name='tenant_id') THEN
        ALTER TABLE payments ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_payments_tenant_id ON payments(tenant_id);
    END IF;
END $$;

-- DeviceEvents 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='device_events' AND column_name='tenant_id') THEN
        ALTER TABLE device_events ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_device_events_tenant_id ON device_events(tenant_id);
    END IF;
END $$;

-- DeviceConfigs 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='device_configs' AND column_name='tenant_id') THEN
        ALTER TABLE device_configs ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_device_configs_tenant_id ON device_configs(tenant_id);
    END IF;
END $$;

-- ChargePointConfigs 表
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='charge_point_configs' AND column_name='tenant_id') THEN
        ALTER TABLE charge_point_configs ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
        CREATE INDEX idx_charge_point_configs_tenant_id ON charge_point_configs(tenant_id);
    END IF;
END $$;

-- ==================== 5. 创建唯一性约束（按租户） ====================

-- Devices: serial_number 按租户唯一
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'unique_tenant_serial_number'
    ) THEN
        ALTER TABLE devices ADD CONSTRAINT unique_tenant_serial_number 
            UNIQUE(tenant_id, serial_number);
    END IF;
END $$;

-- ChargePoints: 如果存在 ocpp_charge_point_id 字段，则按租户唯一
-- 注意：这里假设 charge_points.id 是 UUID 主键，业务标识在另一个字段
-- 如果 id 本身就是业务标识（字符串），则需要 UNIQUE(tenant_id, id)

-- ==================== 6. 启用 RLS ====================

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE end_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_membership_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- 现有业务表启用 RLS
DO $$ 
DECLARE
    table_name TEXT;
    tables TEXT[] := ARRAY[
        'sites', 'charge_points', 'devices', 'orders', 'invoices', 
        'charging_sessions', 'tariffs', 'support_messages', 'evses', 
        'evse_status', 'meter_values', 'pricing_snapshots', 'payments', 
        'device_events', 'device_configs', 'charge_point_configs'
    ];
BEGIN
    FOREACH table_name IN ARRAY tables
    LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = table_name) THEN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        END IF;
    END LOOP;
END $$;

-- ==================== 7. 创建 RLS Policy ====================

-- 标准租户隔离 policy 函数
CREATE OR REPLACE FUNCTION create_tenant_isolation_policy(table_name TEXT) RETURNS VOID AS $$
BEGIN
    EXECUTE format('
        DROP POLICY IF EXISTS tenant_isolation_%s ON %I;
        CREATE POLICY tenant_isolation_%s ON %I
            USING (tenant_id = current_setting(''app.tenant_id'', true)::uuid);
    ', table_name, table_name, table_name, table_name);
END;
$$ LANGUAGE plpgsql;

-- 为所有业务表创建 RLS Policy
DO $$ 
DECLARE
    table_name TEXT;
    tables TEXT[] := ARRAY[
        'sites', 'charge_points', 'devices', 'orders', 'invoices', 
        'charging_sessions', 'tariffs', 'support_messages', 'evses', 
        'evse_status', 'meter_values', 'pricing_snapshots', 'payments', 
        'device_events', 'device_configs', 'charge_point_configs',
        'end_users', 'alerts', 'alert_rules', 'system_configs'
    ];
BEGIN
    FOREACH table_name IN ARRAY tables
    LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = table_name) THEN
            PERFORM create_tenant_isolation_policy(table_name);
        END IF;
    END LOOP;
END $$;

-- 特殊表：tenant_memberships（需要特殊处理，因为需要检查 admin_user_id）
DROP POLICY IF EXISTS tenant_isolation_tenant_memberships ON tenant_memberships;
CREATE POLICY tenant_isolation_tenant_memberships ON tenant_memberships
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- 特殊表：tenant_membership_roles（通过 membership 关联）
DROP POLICY IF EXISTS tenant_isolation_tenant_membership_roles ON tenant_membership_roles;
CREATE POLICY tenant_isolation_tenant_membership_roles ON tenant_membership_roles
    USING (
        EXISTS (
            SELECT 1 FROM tenant_memberships tm
            WHERE tm.id = tenant_membership_roles.membership_id
            AND tm.tenant_id = current_setting('app.tenant_id', true)::uuid
        )
    );

-- 特殊表：roles（系统角色 tenant_id 为 NULL，需要特殊处理）
DROP POLICY IF EXISTS tenant_isolation_roles ON roles;
CREATE POLICY tenant_isolation_roles ON roles
    USING (
        tenant_id IS NULL 
        OR tenant_id = current_setting('app.tenant_id', true)::uuid
    );

-- 特殊表：refresh_tokens（按 user_id 和 user_type 隔离，不按 tenant_id）
-- 但为了安全，我们仍然添加 policy
DROP POLICY IF EXISTS tenant_isolation_refresh_tokens ON refresh_tokens;
-- refresh_tokens 不直接关联 tenant，但可以通过 user_id 关联
-- 这里暂时不添加 policy，或者添加一个宽松的 policy

-- 特殊表：audit_logs（审计日志，允许查看自己租户的日志）
DROP POLICY IF EXISTS tenant_isolation_audit_logs ON audit_logs;
CREATE POLICY tenant_isolation_audit_logs ON audit_logs
    USING (
        tenant_id IS NULL 
        OR tenant_id = current_setting('app.tenant_id', true)::uuid
    );

-- 特殊表：admin_users（管理员用户，不按 tenant_id 隔离，但可以通过 membership 关联）
-- admin_users 本身不存储 tenant_id，所以不需要 RLS policy
-- 或者如果需要，可以通过 membership 关联

-- ==================== 8. 创建系统角色（初始数据） ====================

-- 插入系统默认角色
INSERT INTO roles (id, tenant_id, name, permissions, scope) VALUES
    (gen_random_uuid(), NULL, 'platform_super_admin', 
     '["*"]'::jsonb, 'system')
ON CONFLICT DO NOTHING;

INSERT INTO roles (id, tenant_id, name, permissions, scope) VALUES
    (gen_random_uuid(), NULL, 'tenant_admin', 
     '["tenant.*", "users.*", "charge_points.*", "sites.*", "tariffs.*", "orders.*"]'::jsonb, 'system')
ON CONFLICT DO NOTHING;

INSERT INTO roles (id, tenant_id, name, permissions, scope) VALUES
    (gen_random_uuid(), NULL, 'operator', 
     '["sites.view", "charge_points.view", "tariffs.view", "orders.view", "alerts.*"]'::jsonb, 'system')
ON CONFLICT DO NOTHING;

INSERT INTO roles (id, tenant_id, name, permissions, scope) VALUES
    (gen_random_uuid(), NULL, 'viewer', 
     '["*.view"]'::jsonb, 'system')
ON CONFLICT DO NOTHING;

-- ==================== 9. 创建函数和触发器 ====================

-- 自动更新 updated_at 的函数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 为需要的表创建 updated_at 触发器
DO $$ 
DECLARE
    table_name TEXT;
    tables TEXT[] := ARRAY[
        'tenants', 'admin_users', 'end_users', 'tenant_memberships', 
        'roles', 'alerts', 'alert_rules', 'system_configs'
    ];
BEGIN
    FOREACH table_name IN ARRAY tables
    LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = table_name) THEN
            EXECUTE format('
                DROP TRIGGER IF EXISTS update_%s_updated_at ON %I;
                CREATE TRIGGER update_%s_updated_at
                    BEFORE UPDATE ON %I
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column();
            ', table_name, table_name, table_name, table_name);
        END IF;
    END LOOP;
END $$;

-- ==================== 10. 授予权限 ====================

-- 授予 app_user 和 app_super 角色对表的访问权限
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_super;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_super;

-- 授予未来创建的表和序列的权限
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_super;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_super;

-- ============================================
-- 初始化脚本完成
-- ============================================
