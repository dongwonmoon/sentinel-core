// frontend/src/context/AuthContext.tsx
'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import api, { TokenResponse, UserResponse } from '../lib/api';
import apiClient from '../lib/apiClient';

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

  const logout = useCallback(() => {
    localStorage.removeItem('access_token');
    delete apiClient.defaults.headers.common['Authorization'];
    setToken(null);
    setIsAuthenticated(false);
    setUser(null);
    router.push('/login');
  }, [router]);

  useEffect(() => {
    const loadUser = async () => {
      const storedToken = localStorage.getItem('access_token');
      if (storedToken) {
        apiClient.defaults.headers.common['Authorization'] = `Bearer ${storedToken}`;
        try {
          const userData = await api.getMe();
          setUser(userData);
          setToken(storedToken);
          setIsAuthenticated(true);
        } catch (error) {
          console.error("Failed to fetch user with stored token, logging out.", error);
          logout();
        }
      }
      setLoading(false);
    };

    loadUser();
  }, [logout]);

  const login = async (username: string, password: string) => {
    setLoading(true);
    try {
      const response = await api.login(username, password);
      localStorage.setItem('access_token', response.access_token);
      apiClient.defaults.headers.common['Authorization'] = `Bearer ${response.access_token}`;
      
      const userData = await api.getMe();
      setUser(userData);
      setToken(response.access_token);
      setIsAuthenticated(true);
      
      router.push('/');
    } catch (error) {
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const register = async (username: string, password: string, permission_groups: string[]) => {
    setLoading(true);
    try {
      await api.register({ username, password, permission_groups });
      router.push('/login');
    } catch (error) {
      throw error;
    } finally {
      setLoading(false);
    }
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
