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

export type SourceMetadataValue = string | number | boolean | null | undefined;

export type SourceMetadata = Record<string, SourceMetadataValue>;

export interface Source {
  page_content: string;
  metadata: SourceMetadata;
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
  queryAgent: (
    data: QueryRequest,
    onMessage: (event: MessageEvent) => void,
    onError: (error: Event) => void,
    onClose: () => void
  ): EventSource => {
    const token = localStorage.getItem('access_token');
    const queryParams = new URLSearchParams();
    queryParams.set('query_request', JSON.stringify(data));
    if (token) {
      queryParams.set('token', token);
    }

    const eventSource = new EventSource(
      `${apiClient.defaults.baseURL}/chat/query-stream?${queryParams.toString()}`
    );

    eventSource.onmessage = (event) => {
      onMessage(event);
    };

    eventSource.onerror = (error) => {
      console.error('EventSource failed:', error);
      onError(error);
      eventSource.close(); // Close on error
    };
    
    // The browser will automatically handle closing and reopening, 
    // but we provide a manual close handler from the caller.
    // The 'close' event is not standard in EventSource, so we rely on the caller
    // to manage the closing when the stream is naturally finished by the server.
    // A common pattern is for the server to send a special 'end' event.
    // For now, we'll return the eventSource instance so the caller can close it.

    return eventSource;
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