// frontend/src/lib/api.ts
import apiClient from './apiClient';

// --- Interfaces for API Request/Response ---
// These should ideally match your FastAPI schemas (src/api/schemas.py)

// Auth
export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserCreateRequest {
  username: string;
  password: string;
  permission_groups: string[];
}

export interface UserResponse {
  user_id: number;
  username: string;
  is_active: boolean;
  permission_groups: string[];
}

// Chat
export type ChatMessageRole = 'user' | 'assistant';

export interface ChatMessage {
  role: ChatMessageRole;
  content: string;
}

export interface ChatMessageInDB extends ChatMessage {
  created_at: string; // ISO 8601 string
}

export interface ChatHistoryResponse {
  messages: ChatMessageInDB[];
}

export interface QueryRequest {
  query: string;
  top_k?: number;
  doc_ids_filter?: string[];
  chat_history?: ChatMessage[];
}

export interface Source {
  page_content: string;
  metadata: Record<string, any>;
  score: number;
}

// Documents
export interface GithubRepoRequest {
  repo_url: string;
}

export interface DocumentItem {
  filter_key: string;
  display_name: string;
}

export interface DeleteDocumentRequest {
  doc_id_or_prefix: string;
}

// --- API Functions ---

const api = {
  // Auth Endpoints
  login: async (username: string, password: string): Promise<TokenResponse> => {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    const response = await apiClient.post<TokenResponse>('/auth/token', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
    return response.data;
  },

  register: async (data: UserCreateRequest): Promise<UserResponse> => {
    const response = await apiClient.post<UserResponse>('/auth/register', data);
    return response.data;
  },

  getMe: async (): Promise<UserResponse> => {
    const response = await apiClient.get<UserResponse>('/auth/me');
    return response.data;
  },

  // Chat Endpoints
  getChatHistory: async (): Promise<ChatHistoryResponse> => {
    const response = await apiClient.get<ChatHistoryResponse>('/chat/history');
    return response.data;
  },

  // queryAgent will handle SSE, so it's a bit different
  queryAgent: async (
    data: QueryRequest,
    onMessage: (event: MessageEvent) => void,
    onError: (error: Event) => void,
    onClose: () => void
  ): Promise<void> => {
    const token = localStorage.getItem('access_token');
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(`${apiClient.defaults.baseURL}/chat/query`, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Failed to query agent');
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder('utf-8');

    if (!reader) {
      throw new Error('Failed to get reader for streaming response.');
    }

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        onClose();
        break;
      }
      const chunk = decoder.decode(value, { stream: true });
      // Each chunk might contain multiple SSE messages or partial messages
      chunk.split('\n\n').forEach(message => {
        if (message.startsWith('data: ')) {
          const eventData = message.substring(6);
          try {
            onMessage(new MessageEvent('message', { data: eventData }));
          } catch (e) {
            console.error('Error parsing SSE message:', e, eventData);
          }
        }
      });
    }
  },

  // Document Endpoints
  getDocuments: async (): Promise<Record<string, string>> => {
    const response = await apiClient.get<Record<string, string>>('/documents');
    return response.data;
  },

  uploadFile: async (file: File): Promise<{ status: string; filename: string; message: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post('/documents/upload-and-index', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  indexGithubRepo: async (repo_url: string): Promise<{ status: string; repo_name: string; message: string }> => {
    const response = await apiClient.post('/documents/index-github-repo', { repo_url });
    return response.data;
  },

  deleteDocument: async (doc_id_or_prefix: string): Promise<{ status: string; message: string }> => {
    const response = await apiClient.delete('/documents', { data: { doc_id_or_prefix } });
    return response.data;
  },
};

export default api;