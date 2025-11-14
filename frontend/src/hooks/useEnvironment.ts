const DEFAULT_API = "/api";

export function getApiBaseUrl() {
  const envVar = (import.meta as any).env?.VITE_API_BASE_URL;
  if (!envVar && typeof window !== "undefined") {
    console.warn(
      "VITE_API_BASE_URL이 정의되지 않아 기본값을 사용합니다. (브라우저)",
    );
  }
  return envVar || DEFAULT_API;
}
