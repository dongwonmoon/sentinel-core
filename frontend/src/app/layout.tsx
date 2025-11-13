// frontend/src/app/layout.tsx
import * as React from 'react';
import type { Metadata } from "next";
import { AppRouterCacheProvider } from '@mui/material-nextjs/v13-appRouter';
import "./globals.css";
import { Providers } from './providers'; // Import the new Providers component

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
          <Providers>
            {children}
          </Providers>
        </AppRouterCacheProvider>
      </body>
    </html>
  );
}