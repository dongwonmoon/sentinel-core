import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../lib/apiClient";

export function useDocuments(token: string) {
  return useQuery({
    queryKey: ["documents"],
    queryFn: async () => {
      const timestamp = Date.now().toString();
      return apiRequest<Record<string, string>>(`/documents?t=${timestamp}`, {
        token,
        errorMessage: "문서 목록을 불러오지 못했습니다.",
      });
    },
  });
}
