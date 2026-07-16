"""
Mercado Pago 测试账号配置加载器
用于充电桩模拟器测试支付功能
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class BuyerAccount:
    """买方测试账号"""
    user_id: int
    username: str
    password: str
    email: str


@dataclass
class SellerAccount:
    """卖方测试账号"""
    user_id: int
    username: str
    password: str
    email: str


@dataclass
class AppConfig:
    """Mercado Pago 应用配置"""
    app_id: str
    client_secret: str
    public_key: str
    access_token: str


@dataclass
class TestCard:
    """测试卡信息"""
    number: str
    cvv: str
    expiration_month: str
    expiration_year: str
    holder_name: str


@dataclass
class TestAccountsConfig:
    """测试账号配置"""
    buyer: BuyerAccount
    seller: SellerAccount
    app: AppConfig
    test_cards: Dict[str, TestCard]


def load_test_accounts(config_path: Optional[Path] = None) -> TestAccountsConfig:
    """
    加载测试账号配置
    
    Args:
        config_path: 配置文件路径，默认为 charger-sim/test_accounts.yml
    
    Returns:
        TestAccountsConfig 对象
    """
    if config_path is None:
        # 默认路径：charger-sim/test_accounts.yml
        config_path = Path(__file__).parent.parent / "test_accounts.yml"
    
    if not config_path.exists():
        raise FileNotFoundError(f"Test accounts config not found: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    # 解析买方账号
    buyer_data = data.get("buyer", {})
    buyer = BuyerAccount(
        user_id=buyer_data.get("user_id"),
        username=buyer_data.get("username"),
        password=buyer_data.get("password"),
        email=buyer_data.get("email", f"{buyer_data.get('username')}@test.mercadopago.com"),
    )
    
    # 解析卖方账号
    seller_data = data.get("seller", {})
    seller = SellerAccount(
        user_id=seller_data.get("user_id"),
        username=seller_data.get("username"),
        password=seller_data.get("password"),
        email=seller_data.get("email", f"{seller_data.get('username')}@test.mercadopago.com"),
    )
    
    # 解析应用配置
    app_data = data.get("app", {})
    app = AppConfig(
        app_id=app_data.get("app_id"),
        client_secret=app_data.get("client_secret"),
        public_key=app_data.get("public_key"),
        access_token=app_data.get("access_token"),
    )
    
    # 解析测试卡
    test_cards_data = data.get("test_cards", {})
    test_cards = {}
    for card_name, card_data in test_cards_data.items():
        test_cards[card_name] = TestCard(
            number=card_data.get("number"),
            cvv=card_data.get("cvv"),
            expiration_month=card_data.get("expiration_month"),
            expiration_year=card_data.get("expiration_year"),
            holder_name=card_data.get("holder_name"),
        )
    
    return TestAccountsConfig(
        buyer=buyer,
        seller=seller,
        app=app,
        test_cards=test_cards,
    )


def get_buyer_account(config_path: Optional[Path] = None) -> BuyerAccount:
    """获取买方测试账号"""
    config = load_test_accounts(config_path)
    return config.buyer


def get_seller_account(config_path: Optional[Path] = None) -> SellerAccount:
    """获取卖方测试账号"""
    config = load_test_accounts(config_path)
    return config.seller


def get_app_config(config_path: Optional[Path] = None) -> AppConfig:
    """获取应用配置"""
    config = load_test_accounts(config_path)
    return config.app


def get_test_card(card_name: str, config_path: Optional[Path] = None) -> Optional[TestCard]:
    """获取测试卡信息"""
    config = load_test_accounts(config_path)
    return config.test_cards.get(card_name)
