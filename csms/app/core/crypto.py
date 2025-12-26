#
# 加密工具模块
# 处理设备密码的加密存储和HMAC派生
#

import hashlib
import hmac
import base64
import logging
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import os

logger = logging.getLogger("ocpp_csms")

# 从环境变量获取加密密钥（生产环境必须设置）
_temp_key = Fernet.generate_key().decode()
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", _temp_key)
if ENCRYPTION_KEY == _temp_key:
    logger.warning("使用临时生成的加密密钥，生产环境必须设置ENCRYPTION_KEY环境变量")


def derive_password(master_secret: str, serial_number: str) -> str:
    """
    使用HMAC从master_secret派生设备密码
    
    Args:
        master_secret: 设备类型的master secret（明文或解密后的）
        serial_number: 设备序列号
    
    Returns:
        12位派生密码
    """
    # 使用HMAC-SHA256派生
    key = hmac.new(
        master_secret.encode('utf-8'),
        serial_number.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    # 转换为12位字符串（使用base64编码的前12个字符）
    password = base64.b64encode(key).decode('utf-8')[:12]
    
    return password


def encrypt_master_secret(plain_secret: str) -> str:
    """
    加密master secret
    
    Args:
        plain_secret: 明文master secret
    
    Returns:
        加密后的字符串（base64编码）
    """
    try:
        # 从环境变量获取密钥和salt
        # 生产环境应设置ENCRYPTION_SALT环境变量，否则使用默认值（不推荐）
        salt_str = os.getenv("ENCRYPTION_SALT", "ocpp_csms_salt")
        salt = salt_str.encode()[:16]  # 使用前16字节作为salt
        
        # 从环境变量获取密钥，生成Fernet密钥
        key = base64.urlsafe_b64encode(
            PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            ).derive(ENCRYPTION_KEY.encode())
        )
        
        f = Fernet(key)
        encrypted = f.encrypt(plain_secret.encode())
        return base64.b64encode(encrypted).decode('utf-8')
    except Exception as e:
        logger.error(f"加密master secret失败: {e}", exc_info=True)
        raise


def decrypt_master_secret(encrypted_secret: str) -> str:
    """
    解密master secret
    
    Args:
        encrypted_secret: 加密的master secret（base64编码）
    
    Returns:
        解密后的明文
    """
    try:
        # 从环境变量获取密钥和salt
        # 生产环境应设置ENCRYPTION_SALT环境变量，否则使用默认值（不推荐）
        salt_str = os.getenv("ENCRYPTION_SALT", "ocpp_csms_salt")
        salt = salt_str.encode()[:16]  # 使用前16字节作为salt
        
        # 从环境变量获取密钥，生成Fernet密钥
        key = base64.urlsafe_b64encode(
            PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            ).derive(ENCRYPTION_KEY.encode())
        )
        
        f = Fernet(key)
        encrypted_bytes = base64.b64decode(encrypted_secret.encode())
        decrypted = f.decrypt(encrypted_bytes)
        return decrypted.decode('utf-8')
    except Exception as e:
        logger.error(f"解密master secret失败: {e}", exc_info=True)
        raise
