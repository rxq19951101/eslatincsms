import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
});

export const metadata: Metadata = {
  title: '充电桩运营平台 - 后台管理',
  description: '充电桩运营平台后台管理系统',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark">
      <body className={`${inter.variable} font-sans antialiased bg-slate-950 text-slate-100`}>
        {children}
      </body>
    </html>
  );
}
