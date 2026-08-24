-- 创建初始数据 SQL 脚本
-- 使用原始 SQL，绕过 RLS 检查（在初始化时直接执行）

-- 检查是否已有数据
DO $$
DECLARE
    tenant_count INTEGER;
    admin_count INTEGER;
    tenant_id_val UUID;
    super_admin_id_val UUID;
    tenant_admin_id_val UUID;
    membership_id_val UUID;
    password_hash_val TEXT;
BEGIN
    -- 检查是否已有数据
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
    
    -- 2. 创建超级管理员用户（密码必须由受支持的 Python bootstrap 显式注入）
    -- 注意：这里需要使用实际的密码哈希，但由于我们无法在 SQL 中调用 Python 函数，
    -- 我们将在 Python 脚本中计算哈希值，然后通过参数传入
    -- 这里先创建一个占位符，实际哈希值将在 Python 脚本中设置
    super_admin_id_val := gen_random_uuid();
    tenant_admin_id_val := gen_random_uuid();
    membership_id_val := gen_random_uuid();
    
    -- 注意：密码哈希需要从 Python 脚本传入，这里暂时使用占位符
    -- 实际执行时会通过 Python 脚本替换
    RAISE NOTICE '请使用 Python 脚本 create_initial_data.py 来创建用户（因为需要密码哈希）';
    
    RAISE NOTICE '初始数据创建完成！';
END $$;
