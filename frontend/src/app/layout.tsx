// frontend/src/app/layout.tsx
import * as React from 'react';
import type { Metadata } from "next";
import { AppRouterCacheProvider } from '@mui/material-nextjs/v13-appRouter';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import theme from '../theme'; // Import your custom theme
import "./globals.css"; // Keep global styles
import { AuthProvider } from '../context/AuthContext';
import AuthGuard from '../components/AuthGuard'; // AuthGuard 컴포넌트 임포트

export const metadata: Metadata = {
  title: "Sentinel-Core RAG",
  description: "Enterprise-grade RAG system with advanced capabilities.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <AppRouterCacheProvider options={{ enableCssLayer: true }}>
          <ThemeProvider theme={theme}>
            {/* CssBaseline kickstart an elegant, consistent, and simple baseline to build upon. */}
            <CssBaseline />
            <AuthProvider>
              <AuthGuard>
                {children}
              </AuthGuard>
            </AuthProvider>
          </ThemeProvider>
        </AppRouterCacheProvider>
      </body>
    </html>
  );
}