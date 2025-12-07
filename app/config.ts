/**
 * 本文件定义 App 的 API 配置。
 * 支持多环境自动切换：开发/测试/生产
 * 
 * 配置优先级：
 * 1. 环境变量 EXPO_PUBLIC_CSMS_API_BASE（生产环境）
 * 2. app.config.js 中的 csmsApiBase
 * 3. 根据环境自动选择（开发/测试/生产）
 */

import { Platform } from 'react-native';
import Constants from 'expo-constants';

// 从 app.config.js 的 extra 字段读取配置
const config = Constants.expoConfig?.extra || {};

// 环境配置映射
const ENV_CONFIGS = {
  development: {
    // 开发环境：使用本地 IP 或 localhost
    getApiBase: (computerIp: string) => {
      if (Platform.OS === 'android') {
        // Android 模拟器特殊处理
        // 可以通过环境变量 EXPO_PUBLIC_ANDROID_EMULATOR=true 强制使用 10.0.2.2
        if (process.env.EXPO_PUBLIC_ANDROID_EMULATOR === 'true') {
          return 'http://10.0.2.2:9000';
        }
        return `http://${computerIp}:9000`;
      } else if (Platform.OS === 'ios') {
        // iOS：使用电脑 IP（适用于真机和模拟器）
        return `http://${computerIp}:9000`;
      } else {
        // Web 浏览器：使用 localhost
        return 'http://localhost:9000';
      }
    },
  },
  staging: {
    // 测试环境：使用测试服务器
    getApiBase: () => process.env.EXPO_PUBLIC_STAGING_API_BASE || 
                      config.stagingApiBase || 
                      'https://staging-api.yourdomain.com',
  },
  production: {
    // 生产环境：使用生产服务器
    getApiBase: () => process.env.EXPO_PUBLIC_PROD_API_BASE || 
                      config.prodApiBase || 
                      'https://api.yourdomain.com',
  },
};

/**
 * 获取当前环境
 * 优先级：环境变量 > app.config.js > 自动检测
 */
function getEnvironment(): 'development' | 'staging' | 'production' {
  // 1. 从环境变量读取
  if (process.env.EXPO_PUBLIC_ENV) {
    const env = process.env.EXPO_PUBLIC_ENV.toLowerCase();
    if (['development', 'staging', 'production'].includes(env)) {
      return env as 'development' | 'staging' | 'production';
    }
  }
  
  // 2. 从 app.config.js 读取
  if (config.environment) {
    return config.environment as 'development' | 'staging' | 'production';
  }
  
  // 3. 根据 API 地址自动判断
  const apiBase = process.env.EXPO_PUBLIC_CSMS_API_BASE || config.csmsApiBase;
  if (apiBase) {
    if (apiBase.includes('localhost') || apiBase.includes('192.168') || apiBase.includes('10.0.2.2') || apiBase.includes('127.0.0.1')) {
      return 'development';
    }
    if (apiBase.includes('staging') || apiBase.includes('test')) {
      return 'staging';
    }
    return 'production';
  }
  
  // 4. 默认开发环境
  return 'development';
}

// 获取当前环境
const environment = getEnvironment();

// 获取环境配置
const envConfig = ENV_CONFIGS[environment] || ENV_CONFIGS.development;

// 确定 API 基础地址
let CSMS_API_BASE: string;

// 优先级 1: 直接指定的生产环境 API 地址
if (process.env.EXPO_PUBLIC_CSMS_API_BASE || config.csmsApiBase) {
  CSMS_API_BASE = process.env.EXPO_PUBLIC_CSMS_API_BASE || config.csmsApiBase!;
} else {
  // 优先级 2: 根据环境自动选择
  if (environment === 'development') {
    // 开发环境：使用自动检测的 IP 或配置的 IP
    const computerIp = process.env.EXPO_PUBLIC_COMPUTER_IP || 
                       config.computerIp || 
                       '192.168.20.34';
    CSMS_API_BASE = envConfig.getApiBase(computerIp);
  } else {
    // 测试/生产环境：使用环境配置
    // staging 和 production 的 getApiBase 不需要参数
    CSMS_API_BASE = (envConfig.getApiBase as () => string)();
  }
}

export { CSMS_API_BASE };

export const API_ENDPOINTS = {
  chargers: `${CSMS_API_BASE}/chargers`,
  messages: `${CSMS_API_BASE}/api/messages`,
  remoteStart: `${CSMS_API_BASE}/api/remoteStart`,
  remoteStop: `${CSMS_API_BASE}/api/remoteStop`,
  orders: `${CSMS_API_BASE}/api/orders`,
  currentOrder: `${CSMS_API_BASE}/api/orders/current`,
  currentOrderMeter: `${CSMS_API_BASE}/api/orders/current/meter`,
  health: `${CSMS_API_BASE}/health`,
};

// 打印当前使用的 API 地址，方便调试（必须在 API_ENDPOINTS 定义之后）
console.log(`[Config] ========================================`);
console.log(`[Config] Environment: ${environment}`);
console.log(`[Config] Platform: ${Platform.OS}`);
console.log(`[Config] API Base: ${CSMS_API_BASE}`);
console.log(`[Config] Computer IP: ${config.computerIp || 'N/A'}`);
console.log(`[Config] Chargers endpoint: ${API_ENDPOINTS.chargers}`);
console.log(`[Config] ========================================`);
