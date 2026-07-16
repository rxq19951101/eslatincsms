#!/bin/bash
#
# 使用 psql 直接创建初始数据（绕过 Python ORM 的 RLS 检查）
#

# 生成密码哈希（使用 Python 计算）
PASSWORD_HASH=$(docker compose -f /Users/xiaoqingran/eslatincsms/docker-compose.yml run --rm csms python -c "
from passlib.context import CryptContext
try:
    pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
except:
    pwd_context = CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')
print(pwd_context.hash('admin123'))
" 2>/dev/null)

if [ -z "$PASSWORD_HASH" ]; then
    echo "无法生成密码哈希，使用备用方法"
    exit 1
fi

# 使用 psql 执行 SQL
docker compose -f /Users/xiaoqingran/eslatincsms/docker-compose.yml exec -T db psql -U ocpp_user -d ocpp <<EOF
-- 检查是否已有数据
DO \$\$
DECLARE
    tenant_count INTEGER;
    admin_count INTEGER;
    tenant_id_val UUID;
    super_admin_id_val UUID;
    tenant_admin_id_val UUID;
    membership_id_val UUID;
BEGIN
    SELECT COUNT(*) INTO tenant_count FROM tenants;
    SELECT COUNT(*) INTO admin_count FROM admin_users;
    
    IF tenant_count > 0 OR admin_count > 0 THEN
        RAISE NOTICE '检测到已有数据: 租户 % 个, 管理员 % 个. 跳过初始化.', tenant_count, admin_count;
        RETURN;
    END IF;
    
    RAISE NOTICE '开始创建初始数据...';
    
    -- 1. 创建默认租户
    tenant_id_val := gen_random_uuid();
    INSERT INTO tenants (id, name, domain, status, subscription_plan, max_charge_points, max_users, settings, created_at, updated_at)
    VALUES (tenant_id_val, '默认租户', NULL, 'active', 'premium', 100, 1000, '{}'::jsonb, NOW(), NOW());
    RAISE NOTICE '✓ 租户创建成功: 默认租户 (ID: %)', tenant_id_val;
    
    -- 2. 创建超级管理员用户（密码哈希需要通过 Python 生成）
    super_admin_id_val := gen_random_uuid();
    INSERT INTO admin_users (id, username, email, password_hash, full_name, is_active, is_super_admin, created_at, updated_at)
    VALUES (super_admin_id_val, 'admin', 'admin@example.com', '$PASSWORD_HASH', '系统管理员', TRUE, TRUE, NOW(), NOW());
    RAISE NOTICE '✓ 超级管理员创建成功: admin';
    
    -- 3. 创建租户管理员用户
    tenant_admin_id_val := gen_random_uuid();
    INSERT INTO admin_users (id, username, email, password_hash, full_name, is_active, is_super_admin, created_at, updated_at)
    VALUES (tenant_admin_id_val, 'tenant_admin', 'tenant_admin@example.com', '$PASSWORD_HASH', '租户管理员', TRUE, FALSE, NOW(), NOW());
    
    -- 4. 创建租户成员关系
    membership_id_val := gen_random_uuid();
    INSERT INTO tenant_memberships (id, tenant_id, admin_user_id, is_primary, status, created_at, updated_at)
    VALUES (membership_id_val, tenant_id_val, tenant_admin_id_val, TRUE, 'active', NOW(), NOW());
    RAISE NOTICE '✓ 租户管理员创建成功: tenant_admin';
    
    RAISE NOTICE '初始数据创建完成！';
END \$\$;

-- 显示创建的结果
SELECT '租户列表:' as info;
SELECT id, name, status FROM tenants;

SELECT '管理员用户列表:' as info;
SELECT id, username, email, is_super_admin FROM admin_users;
EOF
