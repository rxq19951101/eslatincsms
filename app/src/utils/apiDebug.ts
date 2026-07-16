/**
 * API调试工具
 */

import { API_BASE_URL, API_ENDPOINTS, DEFAULT_TENANT_ID } from '../constants/config';

export const debugAPIConnection = async () => {
  console.log('=== API连接诊断 ===');
  console.log('API_BASE_URL:', API_BASE_URL);
  console.log('当前环境:', process.env.NODE_ENV);
  console.log('Window location:', typeof window !== 'undefined' ? window.location.href : 'N/A');
  
  // 测试1: 基础连通性
  try {
    console.log('\n测试1: 获取充电站列表...');
    const response = await fetch(`${API_BASE_URL}/api/v1/app/chargers`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    console.log('✅ 状态码:', response.status);
    const data = await response.json();
    console.log('✅ 数据:', data.slice(0, 2)); // 只显示前2条
  } catch (error: any) {
    console.error('❌ 错误:', error.message);
  }
  
  // 测试2: 登录API
  try {
    console.log('\n测试2: 测试登录API...');
    const response = await fetch(`${API_BASE_URL}${API_ENDPOINTS.AUTH.LOGIN_EMAIL}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email: 'test@eslatin.com.co',
        password: 'Test123456',
        tenant_id: DEFAULT_TENANT_ID,
      }),
    });
    console.log('✅ 登录响应状态:', response.status);
    const data = await response.json();
    console.log('✅ Token获取成功:', data.access_token ? '是' : '否');
  } catch (error: any) {
    console.error('❌ 登录错误:', error.message);
  }
  
  console.log('\n=== 诊断完成 ===');
};
