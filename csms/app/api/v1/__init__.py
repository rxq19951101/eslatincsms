#
# API v1路由
# 组织所有v1版本的API端点
#

import logging
import sys
from fastapi import APIRouter

# 确保日志系统已初始化
logger = logging.getLogger("ocpp_csms")
if not logger.handlers:
    # 如果没有处理器，添加一个基本的
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# 创建v1路由器
api_router = APIRouter(prefix="/api/v1", tags=["API v1"])

# 逐个导入并注册路由，即使某个模块失败也继续注册其他模块
# 使用 importlib 动态导入，避免模块级别的导入错误
def register_routes():
    """注册所有路由"""
    import importlib
    
    routes_config = [
        ("chargers", "/chargers", "充电桩管理"),
        ("transactions", "/transactions", "事务管理"),
        ("orders", "/orders", "订单管理"),
        ("ocpp_control", "/ocpp", "OCPP控制"),
        ("admin", "/admin", "管理功能"),
        ("charger_management", "/charger-management", "新充电桩管理"),
        ("statistics", "/statistics", "统计数据"),
    ]
    
    for module_name, prefix, tag in routes_config:
        try:
            # 动态导入模块
            module = importlib.import_module(f"app.api.v1.{module_name}")
            if hasattr(module, 'router'):
                api_router.include_router(module.router, prefix=prefix, tags=[tag])
                logger.info(f"✓ 已注册 /api/v1{prefix} 路由")
            else:
                logger.warning(f"⚠ 模块 app.api.v1.{module_name} 没有 router 属性")
        except ImportError as e:
            logger.error(f"✗ 导入模块 app.api.v1.{module_name} 失败: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"✗ 注册 {module_name} 路由失败: {e}", exc_info=True)

# 执行注册
try:
    register_routes()
except Exception as e:
    logger.error(f"✗ 路由注册过程出错: {e}", exc_info=True)
    # 即使出错也继续，至少 api_router 对象已创建

try:
    from app.api.v1 import transactions
    api_router.include_router(transactions.router, prefix="/transactions", tags=["事务管理"])
    logger.info("✓ 已注册 /api/v1/transactions 路由")
except Exception as e:
    logger.error(f"✗ 注册 transactions 路由失败: {e}", exc_info=True)

try:
    from app.api.v1 import orders
    api_router.include_router(orders.router, prefix="/orders", tags=["订单管理"])
    logger.info("✓ 已注册 /api/v1/orders 路由")
except Exception as e:
    logger.error(f"✗ 注册 orders 路由失败: {e}", exc_info=True)

try:
    from app.api.v1 import ocpp_control
    api_router.include_router(ocpp_control.router, prefix="/ocpp", tags=["OCPP控制"])
    logger.info("✓ 已注册 /api/v1/ocpp 路由")
except Exception as e:
    logger.error(f"✗ 注册 ocpp_control 路由失败: {e}", exc_info=True)

try:
    from app.api.v1 import admin
    api_router.include_router(admin.router, prefix="/admin", tags=["管理功能"])
    logger.info("✓ 已注册 /api/v1/admin 路由")
except Exception as e:
    logger.error(f"✗ 注册 admin 路由失败: {e}", exc_info=True)

try:
    from app.api.v1 import charger_management
    api_router.include_router(charger_management.router, prefix="/charger-management", tags=["新充电桩管理"])
    logger.info("✓ 已注册 /api/v1/charger-management 路由")
except Exception as e:
    logger.error(f"✗ 注册 charger_management 路由失败: {e}", exc_info=True)

try:
    from app.api.v1 import statistics
    api_router.include_router(statistics.router, prefix="/statistics", tags=["统计数据"])
    logger.info("✓ 已注册 /api/v1/statistics 路由")
except Exception as e:
    logger.error(f"✗ 注册 statistics 路由失败: {e}", exc_info=True)

