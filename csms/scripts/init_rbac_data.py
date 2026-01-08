#!/usr/bin/env python3
#
# 初始化RBAC数据脚本
# 创建默认的权限和系统角色
#

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database.base import SessionLocal, init_db
from app.database.models import Permission, Role, RolePermission, Tenant, AdminUser
from app.core.security import get_password_hash
from app.core.id_generator import generate_order_id
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 默认权限定义
DEFAULT_PERMISSIONS = [
    # 仪表板模块
    {"code": "dashboard:view", "name": "查看仪表板", "module": "dashboard", "description": "查看仪表板数据"},
    {"code": "dashboard:export", "name": "导出仪表板数据", "module": "dashboard", "description": "导出仪表板数据"},
    
    # 站点管理模块
    {"code": "sites:view", "name": "查看站点列表", "module": "sites", "description": "查看充电站点列表"},
    {"code": "sites:create", "name": "创建站点", "module": "sites", "description": "创建新的充电站点"},
    {"code": "sites:edit", "name": "编辑站点", "module": "sites", "description": "编辑充电站点信息"},
    {"code": "sites:delete", "name": "删除站点", "module": "sites", "description": "删除充电站点"},
    
    # 充电桩管理模块
    {"code": "chargers:view", "name": "查看充电桩列表", "module": "chargers", "description": "查看充电桩列表"},
    {"code": "chargers:detail", "name": "查看充电桩详情", "module": "chargers", "description": "查看充电桩详细信息"},
    {"code": "chargers:config", "name": "配置充电桩", "module": "chargers", "description": "配置充电桩参数"},
    {"code": "chargers:control", "name": "远程控制充电桩", "module": "chargers", "description": "远程控制充电桩（启动、停止、重启）"},
    {"code": "chargers:create", "name": "创建充电桩", "module": "chargers", "description": "创建新的充电桩"},
    {"code": "chargers:edit", "name": "编辑充电桩", "module": "chargers", "description": "编辑充电桩信息"},
    {"code": "chargers:delete", "name": "删除充电桩", "module": "chargers", "description": "删除充电桩"},
    
    # 订单管理模块
    {"code": "orders:view", "name": "查看订单列表", "module": "orders", "description": "查看充电订单列表"},
    {"code": "orders:detail", "name": "查看订单详情", "module": "orders", "description": "查看订单详细信息"},
    {"code": "orders:refund", "name": "处理退款", "module": "orders", "description": "处理订单退款"},
    {"code": "orders:export", "name": "导出订单", "module": "orders", "description": "导出订单数据"},
    
    # 财务管理模块
    {"code": "finance:view", "name": "查看财务数据", "module": "finance", "description": "查看财务统计数据"},
    {"code": "finance:invoice:create", "name": "创建发票", "module": "finance", "description": "创建发票"},
    {"code": "finance:invoice:export", "name": "导出发票", "module": "finance", "description": "导出发票数据"},
    {"code": "finance:report:view", "name": "查看报表", "module": "finance", "description": "查看财务报表"},
    {"code": "finance:report:export", "name": "导出报表", "module": "finance", "description": "导出财务报表"},
    
    # 定价管理模块
    {"code": "pricing:view", "name": "查看定价规则", "module": "pricing", "description": "查看定价规则列表"},
    {"code": "pricing:create", "name": "创建定价规则", "module": "pricing", "description": "创建新的定价规则"},
    {"code": "pricing:edit", "name": "编辑定价规则", "module": "pricing", "description": "编辑定价规则"},
    {"code": "pricing:delete", "name": "删除定价规则", "module": "pricing", "description": "删除定价规则"},
    
    # 用户管理模块
    {"code": "users:view", "name": "查看用户列表", "module": "users", "description": "查看充电用户列表"},
    {"code": "users:detail", "name": "查看用户详情", "module": "users", "description": "查看用户详细信息"},
    {"code": "users:edit", "name": "编辑用户信息", "module": "users", "description": "编辑用户信息"},
    {"code": "users:freeze", "name": "冻结/解冻用户", "module": "users", "description": "冻结或解冻用户账号"},
    {"code": "users:balance:adjust", "name": "调整用户余额", "module": "users", "description": "调整用户账户余额"},
    
    # 运维管理模块
    {"code": "maintenance:view", "name": "查看工单列表", "module": "maintenance", "description": "查看维护工单列表"},
    {"code": "maintenance:create", "name": "创建工单", "module": "maintenance", "description": "创建维护工单"},
    {"code": "maintenance:assign", "name": "分配工单", "module": "maintenance", "description": "分配维护工单"},
    {"code": "maintenance:resolve", "name": "处理工单", "module": "maintenance", "description": "处理维护工单"},
    
    # 告警管理模块
    {"code": "alerts:view", "name": "查看告警列表", "module": "alerts", "description": "查看告警列表"},
    {"code": "alerts:acknowledge", "name": "确认告警", "module": "alerts", "description": "确认告警"},
    {"code": "alerts:rules:config", "name": "配置告警规则", "module": "alerts", "description": "配置告警规则"},
    
    # 系统设置模块
    {"code": "settings:view", "name": "查看系统设置", "module": "settings", "description": "查看系统配置"},
    {"code": "settings:edit", "name": "编辑系统设置", "module": "settings", "description": "编辑系统配置"},
    {"code": "settings:backup", "name": "数据备份", "module": "settings", "description": "执行数据备份"},
    
    # 权限管理模块（仅超级管理员）
    {"code": "rbac:roles:view", "name": "查看角色列表", "module": "rbac", "description": "查看角色列表"},
    {"code": "rbac:roles:create", "name": "创建角色", "module": "rbac", "description": "创建新角色"},
    {"code": "rbac:roles:edit", "name": "编辑角色", "module": "rbac", "description": "编辑角色信息"},
    {"code": "rbac:roles:delete", "name": "删除角色", "module": "rbac", "description": "删除角色"},
    {"code": "rbac:users:view", "name": "查看管理员用户", "module": "rbac", "description": "查看管理员用户列表"},
    {"code": "rbac:users:create", "name": "创建管理员用户", "module": "rbac", "description": "创建新的管理员用户"},
    {"code": "rbac:users:edit", "name": "编辑管理员用户", "module": "rbac", "description": "编辑管理员用户信息"},
    {"code": "rbac:users:delete", "name": "删除管理员用户", "module": "rbac", "description": "删除管理员用户"},
    {"code": "rbac:permissions:view", "name": "查看权限列表", "module": "rbac", "description": "查看权限列表"},
    
    # 多租户管理模块
    {"code": "tenants:view", "name": "查看租户列表", "module": "tenants", "description": "查看租户列表"},
    {"code": "tenants:create", "name": "创建租户", "module": "tenants", "description": "创建新租户"},
    {"code": "tenants:edit", "name": "编辑租户", "module": "tenants", "description": "编辑租户信息"},
    {"code": "tenants:delete", "name": "删除租户", "module": "tenants", "description": "删除租户"},
    
    # 超级管理员特殊权限
    {"code": "super_admin:cross_tenant", "name": "跨租户访问", "module": "super_admin", "description": "访问所有租户的数据"},
]


# 默认系统角色定义
DEFAULT_ROLES = [
    {
        "name": "超级管理员",
        "code": "super_admin",
        "description": "拥有所有权限，可以访问所有租户数据",
        "permissions": ["*"]  # 所有权限
    },
    {
        "name": "租户管理员",
        "code": "tenant_admin",
        "description": "租户内所有权限",
        "permissions": [
            "dashboard:*", "sites:*", "chargers:*", "orders:*",
            "finance:*", "pricing:*", "users:*", "maintenance:*",
            "alerts:*", "settings:view"
        ]
    },
    {
        "name": "站点管理员",
        "code": "site_manager",
        "description": "指定站点的管理权限",
        "permissions": [
            "dashboard:view", "sites:view", "chargers:view", "chargers:detail",
            "chargers:config", "chargers:control", "orders:view", "orders:detail",
            "maintenance:view", "maintenance:create", "alerts:view", "alerts:acknowledge"
        ]
    },
    {
        "name": "运营专员",
        "code": "operator",
        "description": "充电桩监控、订单处理权限",
        "permissions": [
            "dashboard:view", "chargers:view", "chargers:detail", "chargers:control",
            "orders:view", "orders:detail", "orders:refund", "maintenance:view",
            "alerts:view", "alerts:acknowledge"
        ]
    },
    {
        "name": "客服人员",
        "code": "customer_service",
        "description": "客服消息、用户管理权限",
        "permissions": [
            "dashboard:view", "users:view", "users:detail", "users:edit",
            "orders:view", "orders:detail", "orders:refund"
        ]
    },
    {
        "name": "财务人员",
        "code": "finance",
        "description": "财务报表、发票管理权限",
        "permissions": [
            "dashboard:view", "finance:*", "orders:view", "orders:detail",
            "orders:export"
        ]
    },
    {
        "name": "只读用户",
        "code": "viewer",
        "description": "仅查看权限，无修改权限",
        "permissions": [
            "dashboard:view", "sites:view", "chargers:view", "chargers:detail",
            "orders:view", "orders:detail", "finance:view", "finance:report:view",
            "users:view", "users:detail", "alerts:view"
        ]
    },
]


def init_permissions(db: Session):
    """初始化权限数据"""
    logger.info("开始初始化权限数据...")
    
    created_count = 0
    for perm_data in DEFAULT_PERMISSIONS:
        existing = db.query(Permission).filter(Permission.code == perm_data["code"]).first()
        if not existing:
            permission = Permission(
                code=perm_data["code"],
                name=perm_data["name"],
                description=perm_data.get("description"),
                module=perm_data.get("module"),
                permission_type="function"
            )
            db.add(permission)
            created_count += 1
            logger.info(f"  创建权限: {perm_data['code']}")
        else:
            logger.info(f"  权限已存在: {perm_data['code']}")
    
    db.commit()
    logger.info(f"权限初始化完成，创建了 {created_count} 个新权限")


def init_roles(db: Session):
    """初始化系统角色数据"""
    logger.info("开始初始化系统角色数据...")
    
    # 获取所有权限
    all_permissions = {p.code: p for p in db.query(Permission).all()}
    
    for role_data in DEFAULT_ROLES:
        existing = db.query(Role).filter(
            and_(Role.code == role_data["code"], Role.role_type == "system")
        ).first()
        
        if existing:
            logger.info(f"  角色已存在: {role_data['code']}")
            role = existing
        else:
            role = Role(
                tenant_id=None,  # 系统角色，不属于任何租户
                name=role_data["name"],
                code=role_data["code"],
                description=role_data.get("description"),
                role_type="system",
                status="active"
            )
            db.add(role)
            db.flush()
            logger.info(f"  创建角色: {role_data['code']}")
        
        # 分配权限
        if role_data["permissions"]:
            # 删除旧权限
            db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
            
            # 添加新权限
            for perm_code in role_data["permissions"]:
                if perm_code == "*":
                    # 所有权限
                    for permission in all_permissions.values():
                        role_perm = RolePermission(
                            role_id=role.id,
                            permission_id=permission.id
                        )
                        db.add(role_perm)
                elif perm_code.endswith(":*"):
                    # 模块所有权限
                    prefix = perm_code.replace(":*", "")
                    for code, permission in all_permissions.items():
                        if code.startswith(prefix + ":"):
                            role_perm = RolePermission(
                                role_id=role.id,
                                permission_id=permission.id
                            )
                            db.add(role_perm)
                else:
                    # 具体权限
                    if perm_code in all_permissions:
                        role_perm = RolePermission(
                            role_id=role.id,
                            permission_id=all_permissions[perm_code].id
                        )
                        db.add(role_perm)
        
        db.commit()
    
    logger.info("系统角色初始化完成")


def create_default_tenant_and_admin(db: Session):
    """创建默认租户和超级管理员"""
    logger.info("开始创建默认租户和超级管理员...")
    
    # 创建默认租户
    default_tenant = db.query(Tenant).filter(Tenant.code == "default").first()
    if not default_tenant:
        default_tenant = Tenant(
            id="tenant_default",
            name="默认租户",
            code="default",
            status="active"
        )
        db.add(default_tenant)
        db.commit()
        logger.info("  创建默认租户: default")
    else:
        logger.info("  默认租户已存在")
    
    # 创建超级管理员
    admin_email = "admin@eslatin.com"
    admin_user = db.query(AdminUser).filter(AdminUser.email == admin_email).first()
    if not admin_user:
        admin_user = AdminUser(
            id="admin_001",
            tenant_id=default_tenant.id,
            username="admin",
            email=admin_email,
            password_hash=get_password_hash("admin123"),  # 默认密码，生产环境应修改
            status="active",
            is_super_admin=True
        )
        db.add(admin_user)
        db.commit()
        logger.info(f"  创建超级管理员: {admin_email} (密码: admin123)")
        
        # 分配超级管理员角色
        super_admin_role = db.query(Role).filter(Role.code == "super_admin").first()
        if super_admin_role:
            from app.database.models import AdminUserRole
            user_role = AdminUserRole(
                admin_user_id=admin_user.id,
                role_id=super_admin_role.id
            )
            db.add(user_role)
            db.commit()
            logger.info("  已为超级管理员分配角色")
    else:
        logger.info("  超级管理员已存在")
    
    logger.info("默认租户和超级管理员创建完成")


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始初始化RBAC数据")
    logger.info("=" * 60)
    
    # 初始化数据库表
    try:
        init_db()
        logger.info("数据库表初始化完成")
    except Exception as e:
        logger.error(f"数据库表初始化失败: {e}", exc_info=True)
        return
    
    # 创建数据库会话
    db = SessionLocal()
    try:
        # 初始化权限
        init_permissions(db)
        
        # 初始化角色
        init_roles(db)
        
        # 创建默认租户和超级管理员
        create_default_tenant_and_admin(db)
        
        logger.info("=" * 60)
        logger.info("RBAC数据初始化完成！")
        logger.info("=" * 60)
        logger.info("默认超级管理员账号:")
        logger.info("  邮箱: admin@eslatin.com")
        logger.info("  密码: admin123")
        logger.info("  请在生产环境中立即修改密码！")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"初始化过程出错: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
