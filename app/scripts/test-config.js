#!/usr/bin/env node
/**
 * 测试配置脚本
 * 用于验证 app.config.js 和配置逻辑
 */

const config = require('../app.config.js');

console.log('========================================');
console.log('App 配置测试');
console.log('========================================\n');

console.log('1. app.config.js 配置:');
console.log('   环境:', config.expo.extra.environment);
console.log('   检测到的 IP:', config.expo.extra.computerIp);
console.log('   生产 API 地址:', config.expo.extra.csmsApiBase || '未设置');
console.log('   调试模式:', config.expo.extra.debug);

console.log('\n2. 环境变量测试:');
console.log('   EXPO_PUBLIC_CSMS_API_BASE:', process.env.EXPO_PUBLIC_CSMS_API_BASE || '未设置');
console.log('   EXPO_PUBLIC_COMPUTER_IP:', process.env.EXPO_PUBLIC_COMPUTER_IP || '未设置');
console.log('   EXPO_PUBLIC_ENV:', process.env.EXPO_PUBLIC_ENV || '未设置');
console.log('   NODE_ENV:', process.env.NODE_ENV || 'development');

console.log('\n3. 模拟不同环境:');

// 模拟开发环境
process.env.NODE_ENV = 'development';
delete process.env.EXPO_PUBLIC_CSMS_API_BASE;
const devConfig = require('../app.config.js');
console.log('   开发环境 IP:', devConfig.expo.extra.computerIp);

// 模拟生产环境
process.env.NODE_ENV = 'production';
process.env.EXPO_PUBLIC_CSMS_API_BASE = 'https://api.example.com';
const prodConfig = require('../app.config.js');
console.log('   生产环境 API:', prodConfig.expo.extra.csmsApiBase);

console.log('\n========================================');
console.log('测试完成！');
console.log('========================================\n');

console.log('使用说明:');
console.log('  开发环境: npm start');
console.log('  指定 IP: EXPO_PUBLIC_COMPUTER_IP=192.168.1.100 npm start');
console.log('  生产环境: EXPO_PUBLIC_CSMS_API_BASE=https://api.yourdomain.com npm start');

