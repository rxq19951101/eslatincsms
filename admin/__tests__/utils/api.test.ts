/**
 * API工具函数单元测试
 */
import { getApiBase } from '../app/utils/api';

// Mock window对象
const mockWindow = (hostname: string, protocol: string = 'http:') => {
  Object.defineProperty(window, 'location', {
    value: {
      hostname,
      protocol,
    },
    writable: true,
  });
};

describe('getApiBase', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    // 重置环境变量
    process.env = { ...originalEnv };
    delete process.env.NEXT_PUBLIC_API;
    delete process.env.NEXT_PUBLIC_CSMS_HTTP;
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it('应该优先使用NEXT_PUBLIC_API环境变量', () => {
    process.env.NEXT_PUBLIC_API = 'http://custom-api:8080';
    expect(getApiBase()).toBe('http://custom-api:8080');
  });

  it('应该使用NEXT_PUBLIC_CSMS_HTTP如果NEXT_PUBLIC_API未设置', () => {
    process.env.NEXT_PUBLIC_CSMS_HTTP = 'http://csms-server:9000';
    expect(getApiBase()).toBe('http://csms-server:9000');
  });

  it('在浏览器环境中应该使用localhost（当hostname是localhost）', () => {
    mockWindow('localhost');
    expect(getApiBase()).toBe('http://localhost:9000');
  });

  it('在浏览器环境中应该使用localhost（当hostname是127.0.0.1）', () => {
    mockWindow('127.0.0.1');
    expect(getApiBase()).toBe('http://localhost:9000');
  });

  it('在浏览器环境中应该使用相同的hostname但端口9000', () => {
    mockWindow('192.168.1.100', 'http:');
    expect(getApiBase()).toBe('http://192.168.1.100:9000');
  });

  it('在浏览器环境中应该支持HTTPS协议', () => {
    mockWindow('example.com', 'https:');
    expect(getApiBase()).toBe('https://example.com:9000');
  });

  it('在服务端渲染时应该返回默认值', () => {
    // 模拟服务端环境（没有window对象）
    const originalWindow = global.window;
    // @ts-ignore
    delete global.window;
    
    expect(getApiBase()).toBe('http://localhost:9000');
    
    global.window = originalWindow;
  });
});

