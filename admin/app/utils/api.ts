/**
 * API 配置工具
 * 统一管理 API 基础 URL，支持从环境变量或配置文件获取
 */

/**
 * 获取 API 基础 URL
 * 
 * 优先级：
 * 1. NEXT_PUBLIC_API 环境变量（完整 URL，如 http://192.168.1.100:9000）
 * 2. NEXT_PUBLIC_CSMS_HTTP 环境变量（完整 URL，如 http://192.168.1.100:9000）
 * 3. 如果是客户端，自动检测当前服务器 IP/域名，使用相同的 hostname，端口 9000
 * 4. 默认值（开发环境）
 */
export function getApiBase(): string {
  // 优先使用环境变量（如果设置了完整 URL）
  if (process.env.NEXT_PUBLIC_API) {
    return process.env.NEXT_PUBLIC_API;
  }
  
  if (process.env.NEXT_PUBLIC_CSMS_HTTP) {
    return process.env.NEXT_PUBLIC_CSMS_HTTP;
  }
  
  // 如果是浏览器环境，尝试自动检测服务器 IP/域名
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    const protocol = window.location.protocol; // http: 或 https:
    
    // 如果是 localhost 或 127.0.0.1，使用 localhost（开发环境）
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:9000';
    } else {
      // 生产环境：使用相同的 hostname，但端口为 9000（CSMS 端口）
      // 例如：如果访问 http://192.168.1.100:3000，则 API 为 http://192.168.1.100:9000
      return `${protocol}//${hostname}:9000`;
    }
  }
  
  // 服务端渲染时的默认值（开发环境）
  return 'http://localhost:9000';
}
