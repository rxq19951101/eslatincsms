"""
支付流程模拟模块
用于充电桩模拟器模拟完整的支付流程（先充电后付费）
"""

import asyncio
import logging
import uuid
from typing import Optional, Dict, Any
from decimal import Decimal

import httpx
from simulator.test_accounts import get_app_config, get_test_card

logger = logging.getLogger("eslatin_charger_sim.payment")


async def get_card_token(card_data: Dict[str, str], public_key: str) -> str:
    """
    获取测试卡 token（调用 Mercado Pago API）
    
    Args:
        card_data: 测试卡信息（number, cvv, expiration_month, expiration_year, holder_name）
        public_key: Mercado Pago Public Key
    
    Returns:
        card token ID
    """
    try:
        url = f"https://api.mercadopago.com/v1/card_tokens?public_key={public_key}"
        
        payload = {
            "card_number": card_data["number"].replace(" ", ""),
            "expiration_month": card_data["expiration_month"],
            "expiration_year": card_data["expiration_year"],
            "security_code": card_data["cvv"],
            "cardholder": {
                "name": card_data["holder_name"],
            },
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if "id" in data:
                logger.info(f"Card token created: {data['id'][:20]}...")
                return data["id"]
            else:
                raise ValueError(f"Token creation failed: {data}")
    except Exception as e:
        logger.error(f"Failed to create card token: {e}")
        raise


async def get_session_id_by_transaction(
    transaction_id: int,
    charge_point_id: str,
    backend_api_url: str,
    backend_token: Optional[str] = None,
    max_retries: int = 5,
    retry_delay: int = 2,
) -> Optional[int]:
    """
    通过 transaction_id 查询后端 API 获取 session_id
    
    注意：后端 API 需要通过 qr_token 查询，但模拟器没有 qr_token。
    简化处理：使用 transaction_id 作为 session_id（仅用于测试）。
    或者可以通过查询数据库/API 获取（需要后端支持）。
    
    Args:
        transaction_id: OCPP transaction_id
        charge_point_id: 充电桩 ID
        backend_api_url: 后端 API URL
        backend_token: 后端 API 认证 token（如果需要）
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）
    
    Returns:
        session_id 或 None
    """
    # 简化处理：由于后端 API 需要 qr_token 才能查询会话，
    # 而模拟器没有 qr_token，这里使用 transaction_id 作为 session_id
    # 这仅适用于测试环境，生产环境需要正确的 session_id
    logger.warning(
        f"Using transaction_id as session_id (simplified for testing): "
        f"transaction_id={transaction_id}, charge_point_id={charge_point_id}"
    )
    return transaction_id


async def create_payment_order(
    session_id: int,
    amount: float,
    charge_point_id: str,
    backend_api_url: str,
    card_token: str,
    email: str,
    payment_method_id: str,
    idempotency_key: str,
    backend_token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    调用后端 API 创建支付订单
    
    Args:
        session_id: 充电会话 ID
        amount: 支付金额
        charge_point_id: 充电桩 ID
        backend_api_url: 后端 API URL
        card_token: 卡 token
        email: 用户邮箱
        payment_method_id: 支付方式（如 'visa'）
        idempotency_key: 幂等性键
        backend_token: 后端 API 认证 token（如果需要）
    
    Returns:
        支付订单响应或 None
    """
    try:
        url = f"{backend_api_url.rstrip('/')}/api/v1/app/wallet/payments/create-mp"
        
        payload = {
            "type": "charging",
            "amount": amount,
            "currency": "COP",
            "token": card_token,
            "email": email,
            "payment_method_id": payment_method_id,
            "idempotency_key": idempotency_key,
            "metadata": {
                "session_id": session_id,
                "charge_point_id": charge_point_id,
            },
        }
        
        headers = {"Content-Type": "application/json"}
        if backend_token:
            headers["Authorization"] = f"Bearer {backend_token}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            logger.info(
                f"Payment order created: order_id={data.get('order_id')}, "
                f"payment_id={data.get('payment_id')}, status={data.get('status')}"
            )
            return data
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error creating payment order: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Failed to create payment order: {e}")
        return None


async def wait_for_payment_completion(
    order_id: str,
    backend_api_url: str,
    backend_token: Optional[str] = None,
    timeout: int = 60,
    poll_interval: int = 2,
) -> bool:
    """
    轮询后端 API 查询支付状态，直到完成
    
    Args:
        order_id: 支付订单 ID
        backend_api_url: 后端 API URL
        backend_token: 后端 API 认证 token（如果需要）
        timeout: 超时时间（秒）
        poll_interval: 轮询间隔（秒）
    
    Returns:
        True 如果支付成功，False 如果失败或超时
    """
    try:
        url = f"{backend_api_url.rstrip('/')}/api/v1/app/wallet/payments/{order_id}/status"
        
        headers = {}
        if backend_token:
            headers["Authorization"] = f"Bearer {backend_token}"
        
        start_time = asyncio.get_event_loop().time()
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    logger.warning(f"Payment status check timeout after {timeout}s")
                    return False
                
                try:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    
                    status = data.get("status")
                    logger.debug(f"Payment status: {status} (order_id={order_id})")
                    
                    if status == "approved":
                        logger.info(f"Payment approved: order_id={order_id}")
                        return True
                    elif status in ["declined", "error", "expired", "voided"]:
                        logger.warning(f"Payment failed: status={status}, order_id={order_id}")
                        return False
                    # 继续轮询：created, processing
                    
                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP error checking payment status: {e.response.status_code}")
                    await asyncio.sleep(poll_interval)
                    continue
                except Exception as e:
                    logger.error(f"Error checking payment status: {e}")
                    await asyncio.sleep(poll_interval)
                    continue
                
                await asyncio.sleep(poll_interval)
    except Exception as e:
        logger.error(f"Failed to wait for payment completion: {e}")
        return False


async def simulate_charging_payment(
    session_id: int,
    amount: float,
    charge_point_id: str,
    backend_api_url: str,
    test_card_name: str = "visa_approved",
    payment_delay_seconds: int = 5,
    backend_token: Optional[str] = None,
) -> bool:
    """
    模拟充电支付流程
    
    流程：
    1. 等待几秒（模拟用户操作）
    2. 加载测试账号配置
    3. 获取测试卡信息
    4. 获取 card token
    5. 创建支付订单（调用后端 API）
    6. 轮询支付状态直到完成
    
    Args:
        session_id: 充电会话 ID
        amount: 支付金额（COP）
        charge_point_id: 充电桩 ID
        backend_api_url: 后端 API URL
        test_card_name: 测试卡名称（默认 "visa_approved"）
        payment_delay_seconds: 支付延迟时间（模拟用户操作）
        backend_token: 后端 API 认证 token（如果需要）
    
    Returns:
        True 如果支付成功，False 如果失败
    """
    try:
        logger.info(
            f"Starting payment simulation: session_id={session_id}, "
            f"amount={amount} COP, charge_point_id={charge_point_id}"
        )
        
        # 1. 等待几秒（模拟用户操作）
        if payment_delay_seconds > 0:
            logger.info(f"Waiting {payment_delay_seconds}s before payment (simulating user action)...")
            await asyncio.sleep(payment_delay_seconds)
        
        # 2. 加载测试账号配置
        app_config = get_app_config()
        test_card = get_test_card(test_card_name)
        
        if not test_card:
            logger.error(f"Test card not found: {test_card_name}")
            return False
        
        # 3. 获取 card token
        logger.info("Getting card token from Mercado Pago...")
        card_data = {
            "number": test_card.number,
            "cvv": test_card.cvv,
            "expiration_month": test_card.expiration_month,
            "expiration_year": test_card.expiration_year,
            "holder_name": test_card.holder_name,
        }
        
        card_token = await get_card_token(card_data, app_config.public_key)
        if not card_token:
            logger.error("Failed to get card token")
            return False
        
        # 4. 生成幂等性键
        idempotency_key = str(uuid.uuid4())
        
        # 5. 判断支付方式
        card_number = test_card.number.replace(" ", "")
        payment_method_id = "visa" if card_number.startswith("4") else "master"
        
        # 6. 使用买方账号的邮箱
        from simulator.test_accounts import get_buyer_account
        try:
            buyer_account = get_buyer_account()
            email = buyer_account.email
        except Exception:
            # 如果无法加载，使用默认邮箱
            email = f"testuser@{charge_point_id}.test"
            logger.warning(f"Failed to load buyer account, using default email: {email}")
        
        # 7. 创建支付订单
        logger.info(f"Creating payment order via backend API...")
        payment_result = await create_payment_order(
            session_id=session_id,
            amount=amount,
            charge_point_id=charge_point_id,
            backend_api_url=backend_api_url,
            card_token=card_token,
            email=email,
            payment_method_id=payment_method_id,
            idempotency_key=idempotency_key,
            backend_token=backend_token,
        )
        
        if not payment_result:
            logger.error("Failed to create payment order")
            return False
        
        order_id = payment_result.get("order_id")
        if not order_id:
            logger.error("Payment order created but no order_id returned")
            return False
        
        # 8. 轮询支付状态直到完成
        logger.info(f"Waiting for payment completion: order_id={order_id}")
        success = await wait_for_payment_completion(
            order_id=order_id,
            backend_api_url=backend_api_url,
            backend_token=backend_token,
            timeout=60,
        )
        
        if success:
            logger.info(
                f"Payment simulation completed successfully: "
                f"session_id={session_id}, order_id={order_id}"
            )
        else:
            logger.warning(
                f"Payment simulation failed or timeout: "
                f"session_id={session_id}, order_id={order_id}"
            )
        
        return success
        
    except Exception as e:
        logger.error(f"Payment simulation error: {e}", exc_info=True)
        return False
