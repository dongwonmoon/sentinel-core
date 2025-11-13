// frontend/src/app/providers.tsx
'use client';

import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import theme from '../theme';
import { AuthProvider } from '../context/AuthContext';
import AuthGuard from '../components/AuthGuard';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AuthProvider>
        <AuthGuard>
          {children}
        </AuthGuard>
      </AuthProvider>
    </ThemeProvider>
  );
}
