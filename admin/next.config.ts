import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 启用 standalone 输出模式（用于 Docker）
  output: 'standalone',
};

export default nextConfig;
