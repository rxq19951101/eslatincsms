/**
 * 测试占位符检测功能
 * 在浏览器控制台运行此脚本，模拟不同的hostname场景
 */

// 模拟占位符检测逻辑（从api.ts复制）
const PLACEHOLDER_PATTERNS = [
  'your-server-ip', 'your-ip', 'your-domain', 'example.com',
  'localhost.example', 'placeholder', 'change-me', 'replace-me',
  'your-hostname', 'server-ip', 'server-address',
];

function isPlaceholderUrl(url) {
  const lowerUrl = url.toLowerCase();
  return PLACEHOLDER_PATTERNS.some(pattern => lowerUrl.includes(pattern));
}

function isValidHostname(hostname) {
  if (isPlaceholderUrl(hostname)) return false;
  if (hostname === 'localhost' || hostname === '127.0.0.1') return true;
  const ipv4Regex = /^(\d{1,3}\.){3}\d{1,3}$/;
  if (ipv4Regex.test(hostname)) {
    const parts = hostname.split('.').map(Number);
    return parts.every(part => part >= 0 && part <= 255);
  }
  const domainRegex = /^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/;
  return domainRegex.test(hostname);
}

function getApiBase() {
  // 模拟window.location
  const hostname = window.location.hostname;
  const protocol = window.location.protocol;
  
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://localhost:9000';
  }
  
  if (!isValidHostname(hostname)) {
    return `${protocol}//${hostname}:9000`;
  }
  
  return `${protocol}//${hostname}:9000`;
}

function getApiBaseWithValidation() {
  const url = getApiBase();
  if (isPlaceholderUrl(url)) {
    return {
      url,
      error: `检测到占位符地址: ${url}`
    };
  }
  return { url };
}

// 测试用例
console.log('=== 占位符检测测试 ===\n');

const testCases = [
  { hostname: 'localhost', expected: 'valid' },
  { hostname: '127.0.0.1', expected: 'valid' },
  { hostname: '47.236.134.99', expected: 'valid' },
  { hostname: 'your-server-ip', expected: 'placeholder' },
  { hostname: 'your-ip', expected: 'placeholder' },
  { hostname: '192.168.1.100', expected: 'valid' },
];

testCases.forEach(test => {
  // 临时修改window.location.hostname（仅用于测试）
  const originalHostname = window.location.hostname;
  Object.defineProperty(window.location, 'hostname', {
    writable: true,
    value: test.hostname
  });
  
  const apiBase = getApiBase();
  const validation = getApiBaseWithValidation();
  const isValid = isValidHostname(test.hostname);
  const isPlaceholder = isPlaceholderUrl(test.hostname);
  
  console.log(`测试: ${test.hostname}`);
  console.log(`  有效: ${isValid ? '✅' : '❌'}`);
  console.log(`  占位符: ${isPlaceholder ? '❌' : '✅'}`);
  console.log(`  API地址: ${apiBase}`);
  console.log(`  验证结果: ${validation.error ? '❌ ' + validation.error : '✅ 通过'}`);
  console.log('');
  
  // 恢复原始hostname
  Object.defineProperty(window.location, 'hostname', {
    writable: true,
    value: originalHostname
  });
});

console.log('当前实际配置:');
console.log(`  Hostname: ${window.location.hostname}`);
console.log(`  API地址: ${getApiBase()}`);
console.log(`  验证: ${getApiBaseWithValidation().error || '✅ 配置正确'}`);

