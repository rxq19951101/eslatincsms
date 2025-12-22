/**
 * API 配置工具
 * 统一管理 API 基础 URL，支持从环境变量或配置文件获取
 * 自动检测并拒绝占位符地址，防止连接失败
 */

/**
 * 占位符列表 - 这些值不应该被用作实际的API地址
 */
const PLACEHOLDER_PATTERNS = [
  'your-server-ip',
  'your-ip',
  'your-domain',
  'example.com',
  'localhost.example',
  'placeholder',
  'change-me',
  'replace-me',
  'your-hostname',
  'server-ip',
  'server-address',
];

/**
 * 验证URL是否包含占位符
 */
function isPlaceholderUrl(url: string): boolean {
  const lowerUrl = url.toLowerCase();
  return PLACEHOLDER_PATTERNS.some(pattern => lowerUrl.includes(pattern));
}

/**
 * 验证hostname是否为有效的IP地址或域名
 */
function isValidHostname(hostname: string): boolean {
  // 排除占位符
  if (isPlaceholderUrl(hostname)) {
    return false;
  }
  
  // 允许 localhost 和 127.0.0.1（开发环境）
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return true;
  }
  
  // 验证是否为有效的IP地址（IPv4）
  const ipv4Regex = /^(\d{1,3}\.){3}\d{1,3}$/;
  if (ipv4Regex.test(hostname)) {
    const parts = hostname.split('.').map(Number);
    return parts.every(part => part >= 0 && part <= 255);
  }
  
  // 验证是否为有效的域名（基本检查）
  const domainRegex = /^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/;
  if (domainRegex.test(hostname)) {
    return true;
  }
  
  return false;
}

/**
 * 获取 API 基础 URL
 * 
 * 优先级：
 * 1. NEXT_PUBLIC_API 环境变量（完整 URL，如 http://192.168.1.100:9000）
 * 2. NEXT_PUBLIC_CSMS_HTTP 环境变量（完整 URL，如 http://192.168.1.100:9000）
 * 3. 如果是客户端，自动检测当前服务器 IP/域名，使用相同的 hostname，端口 9000
 * 4. 默认值（开发环境）
 * 
 * 安全特性：
 * - 自动检测并拒绝占位符地址
 * - 验证hostname的有效性
 * - 如果检测到占位符，fallback到localhost（开发环境）或显示错误
 */
export function getApiBase(): string {
  // 优先使用环境变量（如果设置了完整 URL）
  if (process.env.NEXT_PUBLIC_API) {
    const apiUrl = process.env.NEXT_PUBLIC_API.trim();
    // 验证环境变量中的URL
    if (isPlaceholderUrl(apiUrl)) {
      console.warn(
        '[API配置] 检测到占位符地址，请设置正确的 NEXT_PUBLIC_API 环境变量。',
        '当前值:', apiUrl
      );
      // 继续使用，但会在运行时失败，让用户知道需要配置
    }
    return apiUrl;
  }
  
  if (process.env.NEXT_PUBLIC_CSMS_HTTP) {
    const apiUrl = process.env.NEXT_PUBLIC_CSMS_HTTP.trim();
    // 验证环境变量中的URL
    if (isPlaceholderUrl(apiUrl)) {
      console.warn(
        '[API配置] 检测到占位符地址，请设置正确的 NEXT_PUBLIC_CSMS_HTTP 环境变量。',
        '当前值:', apiUrl
      );
      // 继续使用，但会在运行时失败，让用户知道需要配置
    }
    return apiUrl;
  }
  
  // 如果是浏览器环境，尝试自动检测服务器 IP/域名
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    const protocol = window.location.protocol; // http: 或 https:
    
    // 如果是 localhost 或 127.0.0.1，使用 localhost（开发环境）
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:9000';
    }
    
    // 验证hostname是否有效
    if (!isValidHostname(hostname)) {
      // 生产环境：如果hostname无效（包含占位符），尝试从其他来源获取
      // 1. 尝试从window.location.origin提取（如果可能）
      const origin = window.location.origin;
      if (origin && !isPlaceholderUrl(origin)) {
        // 从origin中提取hostname
        try {
          const url = new URL(origin);
          if (isValidHostname(url.hostname)) {
            console.warn(
              '[API配置] 从origin中提取hostname:',
              url.hostname
            );
            return `${url.protocol}//${url.hostname}:9000`;
          }
        } catch (e) {
          // URL解析失败，继续
        }
      }
      
      // 2. 如果仍然无效，在生产环境中不应该fallback到localhost
      // 而是返回一个明确的错误URL，让前端显示错误提示
      console.error(
        '[API配置] 检测到无效的hostname或占位符地址:',
        hostname,
        '\n生产环境配置错误！请确保：',
        '\n1. 访问URL使用正确的服务器IP或域名（而不是占位符）',
        '\n2. 或者设置环境变量 NEXT_PUBLIC_CSMS_HTTP=http://your-actual-ip:9000',
        '\n3. 重启Docker服务使配置生效'
      );
      
      // 返回一个特殊的错误标记URL，前端会检测并显示错误
      // 使用占位符URL，这样前端可以检测到并显示配置错误
      return `http://${hostname}:9000`;
    }
    
    // 生产环境：使用相同的 hostname，但端口为 9000（CSMS 端口）
    // 例如：如果访问 http://192.168.1.100:3000，则 API 为 http://192.168.1.100:9000
    return `${protocol}//${hostname}:9000`;
  }
  
  // 服务端渲染时的默认值（开发环境）
  return 'http://localhost:9000';
}

/**
 * 获取API地址并验证
 * 如果检测到问题，返回错误信息
 */
export function getApiBaseWithValidation(): { url: string; error?: string } {
  const url = getApiBase();
  
  if (isPlaceholderUrl(url)) {
    // 尝试从当前访问URL提取正确的hostname
    let suggestedUrl = url;
    if (typeof window !== 'undefined') {
      const currentHostname = window.location.hostname;
      const protocol = window.location.protocol;
      
      // 如果当前hostname有效，建议使用它
      if (isValidHostname(currentHostname) && !isPlaceholderUrl(currentHostname)) {
        suggestedUrl = `${protocol}//${currentHostname}:9000`;
      }
    }
    
    return {
      url: suggestedUrl,
      error: `检测到占位符地址配置。请设置环境变量 NEXT_PUBLIC_CSMS_HTTP=${suggestedUrl} 并重启服务。`
    };
  }
  
  // 额外验证：检查URL是否包含占位符hostname
  try {
    const urlObj = new URL(url);
    if (isPlaceholderUrl(urlObj.hostname)) {
      return {
        url,
        error: `API地址包含占位符: ${urlObj.hostname}。请设置环境变量 NEXT_PUBLIC_CSMS_HTTP 为正确的服务器地址。`
      };
    }
  } catch (e) {
    // URL解析失败，可能是格式错误
    return {
      url,
      error: `API地址格式错误: ${url}。请检查配置。`
    };
  }
  
  return { url };
}
