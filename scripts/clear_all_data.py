#!/usr/bin/env python3
#
# 清除所有数据库和Redis数据
# 用于测试前清理环境
#

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import redis

# 从环境变量获取数据库和Redis连接信息
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ocpp_user:ocpp_password@localhost:5432/ocpp")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def clear_database():
    """清除数据库所有数据"""
    try:
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        print("正在清除数据库数据...")
        
        # 获取所有表名
        result = session.execute(text("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
        """))
        tables = [row[0] for row in result]
        
        if not tables:
            print("  没有找到表")
            return
        
        # 禁用外键约束检查
        session.execute(text("SET session_replication_role = 'replica'"))
        
        # 删除所有表的数据
        for table in tables:
            try:
                session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                print(f"  ✓ 已清除表: {table}")
            except Exception as e:
                print(f"  ⚠️  清除表 {table} 失败: {e}")
        
        # 恢复外键约束检查
        session.execute(text("SET session_replication_role = 'origin'"))
        session.commit()
        
        print("✓ 数据库数据已清除")
        
    except Exception as e:
        print(f"❌ 清除数据库失败: {e}")
        sys.exit(1)
    finally:
        if 'session' in locals():
            session.close()


def clear_redis():
    """清除Redis所有数据"""
    try:
        print("正在清除Redis数据...")
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.flushall()
        print("✓ Redis数据已清除")
    except Exception as e:
        print(f"❌ 清除Redis失败: {e}")
        sys.exit(1)


def main():
    """主函数"""
    print("=" * 60)
    print("清除所有数据")
    print("=" * 60)
    print()
    
    # 确认操作
    confirm = input("确定要清除所有数据吗？(yes/no): ")
    if confirm.lower() != "yes":
        print("操作已取消")
        return
    
    print()
    
    # 清除数据库
    clear_database()
    print()
    
    # 清除Redis
    clear_redis()
    print()
    
    print("=" * 60)
    print("✓ 所有数据已清除")
    print("=" * 60)


if __name__ == "__main__":
    main()

