#
# 管理功能API
# 提供系统管理相关的API端点
#

from fastapi import APIRouter
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


@router.get("/system/info", summary="系统信息")
def get_system_info():
    """获取系统信息"""
    logger.info("[API] GET /api/v1/admin/system/info | 获取系统信息")
    
    from app.core.config import get_settings
    settings = get_settings()
    
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }

