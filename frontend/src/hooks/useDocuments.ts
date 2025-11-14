import { useQuery } from "@tanstack/react-query";
import { getApiBaseUrl } from "./useEnvironment";

const API_BASE = getApiBaseUrl();

export function useDocuments(token: string) {
  return useQuery({
    queryKey: ["documents"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/documents`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!res.ok) throw new Error("문서 목록을 불러오지 못했습니다.");
      return res.json() as Promise<Record<string, string>>;
    },
  });
}
