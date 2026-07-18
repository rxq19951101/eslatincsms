import type { Metadata } from 'next';
import './globals.css';
import { I18nProvider } from '@/lib/i18n';

export const metadata: Metadata = {
  title: 'EsLatin - Admin Portal',
  description: 'EsLatin charging operations platform',
  icons: {
    icon: '/favicon.svg',
    shortcut: '/favicon.svg',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark" suppressHydrationWarning>
      <body
        className="font-sans antialiased bg-slate-950 text-slate-100"
        suppressHydrationWarning
      >
        <I18nProvider>{children}</I18nProvider>
      </body>
    </html>
  );
}
