// frontend/src/lib/apiClient.ts
import axios from 'axios';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add the JWT token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle 401 errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      // Handle unauthorized errors, e.g., redirect to login page
      localStorage.removeItem('access_token');
      // You might want to use Next.js router here, but for a lib file,
      // a simple window.location.href is often used or handled by a global error context.
      // For now, we'll just remove the token.
      console.error('Unauthorized: Token expired or invalid. Please log in again.');
      // window.location.href = '/login'; // This would cause a full page reload
    }
    return Promise.reject(error);
  }
);

export default apiClient;
