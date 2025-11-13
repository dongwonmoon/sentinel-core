// frontend/src/context/AuthContext.tsx
'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import api, { TokenResponse, UserResponse } from '../lib/api';

interface AuthContextType {
  isAuthenticated: boolean;
  user: UserResponse | null;
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, permission_groups: string[]) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [user, setUser] = useState<UserResponse | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const router = useRouter();

  useEffect(() => {
    const storedToken = localStorage.getItem('access_token');
    // In a real app, you'd validate the token (e.g., by calling a /me endpoint)
    if (storedToken) {
      setToken(storedToken);
      setIsAuthenticated(true);
      // For now, we don't have a /me endpoint, so user info is not loaded here.
      // In a real app, you'd fetch user details here.
    }
    setLoading(false);
  }, []);

  const login = async (username: string, password: string) => {
    setLoading(true);
    try {
      const response: TokenResponse = await api.login(username, password);
      localStorage.setItem('access_token', response.access_token);
      setToken(response.access_token);
      setIsAuthenticated(true);
      // In a real app, fetch user details after login
      // For now, set a dummy user
      setUser({ user_id: 1, username: username, is_active: true, permission_groups: ['all_users'] });
      router.push('/'); // Redirect to home page
    } finally {
      setLoading(false);
    }
  };

  const register = async (username: string, password: string, permission_groups: string[]) => {
    setLoading(true);
    try {
      const response: UserResponse = await api.register({ username, password, permission_groups });
      // After successful registration, you might want to automatically log them in
      // For now, just redirect to login page
      router.push('/login');
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    setToken(null);
    setIsAuthenticated(false);
    setUser(null);
    router.push('/login'); // Redirect to login page
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, user, token, login, register, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
