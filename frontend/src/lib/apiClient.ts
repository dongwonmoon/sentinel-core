import { getApiBaseUrl } from "../hooks/useEnvironment";

const API_BASE = getApiBaseUrl();

type ApiRequestOptions = Omit<RequestInit, "body" | "headers"> & {
  headers?: HeadersInit;
  body?: BodyInit;
  token?: string;
  /**
   * Optional helper for JSON payloads. When provided the body
   * will be stringified and the Content-Type header is set.
   */
  json?: Record<string, unknown>;
  errorMessage?: string;
};

/**
 * Small wrapper around fetch that keeps authorization and error handling
 * consistent across the UI.
 */
export async function apiRequest<T = void>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const { token, json, errorMessage, headers, body, ...rest } = options;
  const finalHeaders = new Headers(headers);

  if (token) {
    finalHeaders.set("Authorization", `Bearer ${token}`);
  }

  const init: RequestInit = {
    ...rest,
    headers: finalHeaders,
  };

  if (json) {
    finalHeaders.set("Content-Type", "application/json");
    init.body = JSON.stringify(json);
  } else if (body) {
    init.body = body;
  }

  const response = await fetch(`${API_BASE}${path}`, init);

  if (!response.ok) {
    throw new Error(errorMessage ?? `요청에 실패했습니다. (${response.status})`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
