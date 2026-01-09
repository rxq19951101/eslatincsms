#
# 系统配置服务
# 管理全局和租户级别的配置
#

from typing import Optional, Any
from uuid import UUID
from sqlalchemy.orm import Session
from app.database.models import SystemConfig
from app.core.logging_config import get_logger
import json

logger = get_logger("ocpp_csms")


class ConfigService:
    """系统配置服务"""
    
    @staticmethod
    def get_config(
        db: Session,
        config_key: str,
        tenant_id: Optional[UUID] = None,
        default: Any = None
    ) -> Any:
        """
        获取配置值
        
        优先级：
        1. 租户配置（如果提供了 tenant_id）
        2. 全局配置（tenant_id 为 NULL）
        3. 默认值
        """
        # 先查找租户配置
        if tenant_id:
            config = db.query(SystemConfig).filter(
                SystemConfig.tenant_id == tenant_id,
                SystemConfig.config_key == config_key
            ).first()
            if config:
                return ConfigService._parse_config_value(config.config_value, config.value_type)
        
        # 查找全局配置
        config = db.query(SystemConfig).filter(
            SystemConfig.tenant_id.is_(None),
            SystemConfig.config_key == config_key
        ).first()
        
        if config:
            return ConfigService._parse_config_value(config.config_value, config.value_type)
        
        return default
    
    @staticmethod
    def set_config(
        db: Session,
        config_key: str,
        config_value: Any,
        value_type: str = "string",
        tenant_id: Optional[UUID] = None,
        description: Optional[str] = None
    ) -> SystemConfig:
        """设置配置值"""
        # 查找现有配置
        config = db.query(SystemConfig).filter(
            SystemConfig.tenant_id == (tenant_id if tenant_id else None),
            SystemConfig.config_key == config_key
        ).first()
        
        # 转换值为字符串
        value_str = ConfigService._serialize_config_value(config_value, value_type)
        
        if config:
            # 更新现有配置
            config.config_value = value_str
            config.value_type = value_type
            if description is not None:
                config.description = description
        else:
            # 创建新配置
            config = SystemConfig(
                tenant_id=tenant_id,
                config_key=config_key,
                config_value=value_str,
                value_type=value_type,
                description=description
            )
            db.add(config)
        
        db.commit()
        db.refresh(config)
        
        logger.info(f"Set config: {config_key} (tenant: {tenant_id})")
        return config
    
    @staticmethod
    def delete_config(
        db: Session,
        config_key: str,
        tenant_id: Optional[UUID] = None
    ) -> bool:
        """删除配置"""
        config = db.query(SystemConfig).filter(
            SystemConfig.tenant_id == (tenant_id if tenant_id else None),
            SystemConfig.config_key == config_key
        ).first()
        
        if not config:
            return False
        
        db.delete(config)
        db.commit()
        
        logger.info(f"Deleted config: {config_key} (tenant: {tenant_id})")
        return True
    
    @staticmethod
    def list_configs(
        db: Session,
        tenant_id: Optional[UUID] = None
    ) -> list:
        """获取配置列表"""
        query = db.query(SystemConfig)
        
        if tenant_id is not None:
            # 获取租户配置和全局配置
            query = query.filter(
                (SystemConfig.tenant_id == tenant_id) | (SystemConfig.tenant_id.is_(None))
            )
        else:
            # 只获取全局配置
            query = query.filter(SystemConfig.tenant_id.is_(None))
        
        configs = query.all()
        
        result = []
        for config in configs:
            result.append({
                "id": str(config.id),
                "tenant_id": str(config.tenant_id) if config.tenant_id else None,
                "config_key": config.config_key,
                "config_value": ConfigService._parse_config_value(config.config_value, config.value_type),
                "value_type": config.value_type,
                "description": config.description
            })
        
        return result
    
    @staticmethod
    def _parse_config_value(value_str: str, value_type: str) -> Any:
        """解析配置值"""
        if value_str is None:
            return None
        
        if value_type == "integer" or value_type == "int":
            return int(value_str)
        elif value_type == "float":
            return float(value_str)
        elif value_type == "bool":
            return value_str.lower() in ("true", "1", "yes")
        elif value_type == "json":
            return json.loads(value_str)
        else:
            return value_str
    
    @staticmethod
    def _serialize_config_value(value: Any, value_type: str) -> str:
        """序列化配置值"""
        if value_type == "json":
            return json.dumps(value)
        else:
            return str(value)
