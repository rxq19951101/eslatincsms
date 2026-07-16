#!/bin/bash
#
# 创建初始数据的 Shell 脚本
# 使用 psql 直接执行 SQL，绕过 Python ORM 的 RLS 检查
#

echo "正在创建初始数据..."

# 生成密码哈希
PASSWORD_HASH=$(docker compose -f docker-compose.yml run --rm csms python -c "
from passlib.context import CryptContext
try:
    pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
except:
    pwd_context = CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')
print(pwd_context.hash('admin123'))
" 2>/dev/null | tail -1)

if [ -z "$PASSWORD_HASH" ]; then
    echo "❌ 无法生成密码哈希"
    exit 1
fi

# 使用 psql 执行 SQL
docker compose -f docker-compose.yml exec -T db psql -U ocpp_user -d ocpp <<EOF
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
    
    tenant_id_val := gen_random_uuid();
    INSERT INTO tenants (id, name, domain, status, subscription_plan, max_charge_points, max_users, settings, created_at, updated_at)
    VALUES (tenant_id_val, '默认租户', NULL, 'active', 'premium', 100, 1000, '{}'::jsonb, NOW(), NOW());
    RAISE NOTICE '✓ 租户创建成功: 默认租户';
    
    super_admin_id_val := gen_random_uuid();
    INSERT INTO admin_users (id, username, email, password_hash, full_name, is_active, is_super_admin, created_at, updated_at)
    VALUES (super_admin_id_val, 'admin', 'admin@example.com', '$PASSWORD_HASH', '系统管理员', TRUE, TRUE, NOW(), NOW());
    RAISE NOTICE '✓ 超级管理员创建成功: admin';
    
    tenant_admin_id_val := gen_random_uuid();
    INSERT INTO admin_users (id, username, email, password_hash, full_name, is_active, is_super_admin, created_at, updated_at)
    VALUES (tenant_admin_id_val, 'tenant_admin', 'tenant_admin@example.com', '$PASSWORD_HASH', '租户管理员', TRUE, FALSE, NOW(), NOW());
    
    membership_id_val := gen_random_uuid();
    INSERT INTO tenant_memberships (id, tenant_id, admin_user_id, is_primary, status, created_at, updated_at)
    VALUES (membership_id_val, tenant_id_val, tenant_admin_id_val, TRUE, 'active', NOW(), NOW());
    RAISE NOTICE '✓ 租户管理员创建成功: tenant_admin';
    
    RAISE NOTICE '初始数据创建完成！';
END \$\$;
EOF

echo ""
echo "✓ 初始数据创建完成！"
echo ""
echo "默认账号信息："
echo "-" * 50
echo "超级管理员:"
echo "  用户名: admin"
echo "  密码: admin123"
echo "  邮箱: admin@example.com"
echo "-" * 50
echo "租户管理员:"
echo "  用户名: tenant_admin"
echo "  密码: admin123"
echo "  邮箱: tenant_admin@example.com"
