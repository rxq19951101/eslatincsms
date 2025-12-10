/**
 * Expo App 动态配置文件
 * 支持自动检测本机 IP 地址和环境变量配置
 */

const { name, slug, version, orientation, platforms, splash, ios, android, web } = require('./app.json').expo;

/**
 * 自动检测本机 IP 地址（开发环境）
 * 返回第一个非回环的 IPv4 地址
 */
function getLocalIp() {
  try {
    const os = require('os');
    const interfaces = os.networkInterfaces();
    
    // 遍历所有网络接口
    for (const name of Object.keys(interfaces)) {
      for (const iface of interfaces[name]) {
        // 查找 IPv4 地址，排除回环地址
        if (iface.family === 'IPv4' && !iface.internal) {
          return iface.address;
        }
      }
    }
  } catch (error) {
    console.warn('无法自动检测 IP 地址:', error);
  }
  
  // 如果无法检测，返回默认值
  return '192.168.20.34';
}

// 获取当前环境
// 默认使用 production 环境，连接到远程服务器 47.236.134.99
// 如果需要本地开发，可以通过环境变量 EXPO_PUBLIC_ENV=development 切换
const environment = process.env.EXPO_PUBLIC_ENV || process.env.NODE_ENV || 'production';

// 自动检测本机 IP（仅在开发环境）
const detectedIp = environment === 'development' ? getLocalIp() : null;

// ========== 服务器配置 ==========
// 在这里设置你的服务器 IP 地址（修改下面这行）
const SERVER_IP = process.env.SERVER_IP || '47.236.134.99';  // 生产服务器 IP
const SERVER_PORT = process.env.SERVER_PORT || '9000';
const SERVER_API_BASE = `http://${SERVER_IP}:${SERVER_PORT}`;
// =================================

module.exports = {
  expo: {
    name,
    slug,
    version,
    orientation,
    platforms,
    splash,
    ios,
    android,
    web,
    
    // 额外配置，可以通过 Constants.expoConfig.extra 访问
    extra: {
      // 生产环境 API 地址（优先级最高）
      // 优先级: 环境变量 EXPO_PUBLIC_CSMS_API_BASE > 配置文件中的 SERVER_API_BASE > 自动检测
      csmsApiBase: process.env.EXPO_PUBLIC_CSMS_API_BASE || SERVER_API_BASE || null,
      
      // 开发环境 IP 地址
      // 优先级: 环境变量 > 自动检测 > 默认值
      computerIp: process.env.EXPO_PUBLIC_COMPUTER_IP || detectedIp || '192.168.20.34',
      
      // 环境标识
      environment: environment,
      
      // 调试信息
      debug: process.env.EXPO_PUBLIC_DEBUG === 'true',
    },
  },
};

