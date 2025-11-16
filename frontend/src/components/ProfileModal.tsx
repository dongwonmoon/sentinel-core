// frontend/src/components/ProfileModal.tsx (신규 파일)
import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../lib/apiClient";
import { notify } from "./NotificationHost";
import { useAuth } from "../providers/AuthProvider";
import Modal from "./Modal";

type Props = {
  onClose: () => void;
};

// 백엔드 /chat/profile API의 응답 형태
type ProfileResponse = {
  profile_text: string;
};

export default function ProfileModal({ onClose }: Props) {
  const { user, token } = useAuth();
  if (!user || !token) return null;

  const queryClient = useQueryClient();
  const [profileText, setProfileText] = useState("");

  // 1. useQuery로 프로필 데이터 로드
  const { data, isLoading: isQueryLoading } = useQuery({
    queryKey: ["profile"],
    queryFn: () =>
      apiRequest<ProfileResponse>("/chat/profile", {
        token: token,
        errorMessage: "프로필 로딩 실패",
      }),
  });

  // 2. 로드된 데이터를 로컬 state에 동기화
  useEffect(() => {
    if (data?.profile_text) {
      setProfileText(data.profile_text);
    }
  }, [data]);

  // 3. useMutation으로 프로필 저장
  const { mutate, isPending: isMutationPending } = useMutation({
    mutationFn: (text: string) =>
      apiRequest("/chat/profile", {
        method: "POST",
        token: token,
        json: { profile_text: text },
        errorMessage: "프로필 저장 실패",
      }),
    onSuccess: () => {
      notify("프로필이 저장되었습니다.");
      queryClient.invalidateQueries({ queryKey: ["profile"] }); // 캐시 갱신
      onClose();
    },
    onError: (err) => {
      notify(err.message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutate(profileText);
  };

  const isLoading = isQueryLoading || isMutationPending;

  return (
    <Modal onClose={onClose}>
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <h2>내 프로필</h2>
        <p className="muted">
          에이전트가 참고할 당신의 역할, 선호도 등을 자유롭게 입력하세요. (e.g.,
          "나는 파이썬 백엔드 개발자이며, FastAPI를 선호합니다.")
        </p>
        <textarea
          value={profileText}
          onChange={(e) => setProfileText(e.target.value)}
          placeholder="프로필을 입력하세요..."
          rows={8}
          disabled={isLoading}
        />
        <div style={{ display: "flex", gap: "1rem", justifyContent: "flex-end" }}>
          <button
            type="button"
            className="ghost"
            onClick={onClose}
            disabled={isLoading}
          >
            취소
          </button>
          <button type="submit" className="primary" disabled={isLoading}>
            {isLoading ? "저장 중..." : "저장"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
