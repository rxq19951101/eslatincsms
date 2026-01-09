#
# 系统配置管理API
# 提供配置的CRUD操作
#

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional, Any
from uuid import UUID
from app.database.base import get_db, tenant_id_context
from app.core.auth import get_current_user
from app.core.permissions import get_current_admin_user
from app.services.config_service import ConfigService
from app.database.models import SystemConfig
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求/响应模型 ====================

class SetConfigRequest(BaseModel):
    config_key: str
    config_value: Any
    value_type: str = "string"
    description: Optional[str] = None


class ConfigResponse(BaseModel):
    id: str
    tenant_id: Optional[str]
    config_key: str
    config_value: Any
    value_type: str
    description: Optional[str]
    created_at: str
    updated_at: str


# ==================== 配置端点 ====================

@router.get("", response_model=List[ConfigResponse], summary="获取配置列表")
async def list_configs(
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """获取配置列表（租户配置 + 全局配置）"""
    tenant_id = tenant_id_context.get()
    
    configs = ConfigService.list_configs(db=db, tenant_id=tenant_id)
    
    # 从数据库查询完整信息
    result = []
    for config_dict in configs:
        config_key = config_dict["config_key"]
        config_obj = db.query(SystemConfig).filter(
            SystemConfig.tenant_id == (UUID(config_dict["tenant_id"]) if config_dict["tenant_id"] else None),
            SystemConfig.config_key == config_key
        ).first()
        
        if config_obj:
            result.append(ConfigResponse(
                id=str(config_obj.id),
                tenant_id=str(config_obj.tenant_id) if config_obj.tenant_id else None,
                config_key=config_obj.config_key,
                config_value=ConfigService._parse_config_value(config_obj.config_value, config_obj.value_type),
                value_type=config_obj.value_type,
                description=config_obj.description,
                created_at=config_obj.created_at.isoformat() if config_obj.created_at else "",
                updated_at=config_obj.updated_at.isoformat() if config_obj.updated_at else ""
            ))
    
    return result


@router.get("/{config_key}", summary="获取配置值")
async def get_config(
    config_key: str,
    default: Optional[str] = Query(None),
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """获取配置值"""
    tenant_id = tenant_id_context.get()
    
    value = ConfigService.get_config(
        db=db,
        config_key=config_key,
        tenant_id=tenant_id,
        default=default
    )
    
    return {
        "config_key": config_key,
        "config_value": value,
        "tenant_id": str(tenant_id) if tenant_id else None
    }


@router.post("", response_model=ConfigResponse, summary="设置配置")
async def set_config(
    request_data: SetConfigRequest,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """设置配置值"""
    tenant_id = tenant_id_context.get()
    
    config = ConfigService.set_config(
        db=db,
        config_key=request_data.config_key,
        config_value=request_data.config_value,
        value_type=request_data.value_type,
        tenant_id=tenant_id,
        description=request_data.description
    )
    
    return ConfigResponse(
        id=str(config.id),
        tenant_id=str(config.tenant_id) if config.tenant_id else None,
        config_key=config.config_key,
        config_value=ConfigService._parse_config_value(config.config_value, config.value_type),
        value_type=config.value_type,
        description=config.description,
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else ""
    )


@router.delete("/{config_key}", summary="删除配置")
async def delete_config(
    config_key: str,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """删除配置"""
    tenant_id = tenant_id_context.get()
    
    success = ConfigService.delete_config(
        db=db,
        config_key=config_key,
        tenant_id=tenant_id
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Config not found")
    
    return {"message": "Config deleted successfully"}
