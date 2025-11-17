/**
 * @file 사용자 프로필을 조회하고 수정하는 모달(Modal) 컴포넌트입니다.
 * @description 이 컴포넌트는 사용자의 프로필 정보(역할, 선호도 등)를
 * LLM 에이전트가 참고할 수 있도록 관리하는 UI를 제공합니다.
 * TanStack Query(React Query)를 사용하여 서버 상태(프로필 데이터)를 관리합니다.
 */
import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../lib/apiClient";
import { notify } from "./NotificationHost";
import { useAuth } from "../providers/AuthProvider";
import Modal from "./Modal";

/** ProfileModal 컴포넌트가 받는 props의 타입을 정의합니다. */
type Props = {
  /** 모달을 닫을 때 호출될 콜백 함수 */
  onClose: () => void;
};

// 백엔드 /chat/profile API의 응답 형태
/** 백엔드 `/chat/profile` API의 응답 본문 타입을 정의합니다. */
type ProfileResponse = {
  profile_text: string;
};

export default function ProfileModal({ onClose }: Props) {
  // --- 1. 훅 및 상태 초기화 ---
  const { user, token } = useAuth();
  // QueryClient 인스턴스를 가져와, 캐시 무효화 등에 사용합니다.
  const queryClient = useQueryClient();
  // 사용자가 textarea에 입력하는 텍스트를 관리하는 로컬 상태
  const [profileText, setProfileText] = useState("");

  // 방어적 코딩: 인증 정보가 없으면 컴포넌트를 렌더링하지 않습니다.
  if (!user || !token) return null;

  // --- 2. 데이터 페칭 (useQuery) ---
  // `useQuery`를 사용하여 서버로부터 프로필 데이터를 가져옵니다.
  // - `queryKey`: 이 쿼리의 고유 식별자입니다. 다른 곳에서 이 키로 캐시를 관리할 수 있습니다.
  // - `queryFn`: 실제 데이터 페칭을 수행하는 비동기 함수입니다.
  const { data, isLoading: isQueryLoading } = useQuery({
    queryKey: ["profile"],
    queryFn: () =>
      apiRequest<ProfileResponse>("/chat/profile", {
        token: token,
        errorMessage: "프로필 로딩 실패",
      }),
  });

  // `useQuery`로 데이터를 성공적으로 가져왔을 때,
  // 해당 데이터를 로컬 `profileText` 상태에 동기화하는 `useEffect` 훅입니다.
  useEffect(() => {
    if (data?.profile_text) {
      setProfileText(data.profile_text);
    }
  }, [data]); // `data`가 변경될 때만 이 효과를 실행합니다.

  // --- 3. 데이터 변경 (useMutation) ---
  // `useMutation`을 사용하여 서버의 데이터를 변경(생성/수정/삭제)합니다.
  // - `mutationFn`: 실제 데이터 변경 API를 호출하는 비동기 함수입니다.
  // - `onSuccess`: 뮤테이션이 성공적으로 완료되었을 때 실행될 콜백입니다.
  // - `onError`: 뮤테이션이 실패했을 때 실행될 콜백입니다.
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
      // `invalidateQueries`를 호출하여 'profile' 키를 가진 쿼리 캐시를 무효화합니다.
      // 이를 통해 다음에 프로필 모달을 열 때 새로운 데이터를 다시 가져오게 됩니다.
      queryClient.invalidateQueries({ queryKey: ["profile"] });
      onClose(); // 모달을 닫습니다.
    },
    onError: (err) => {
      // 에러 발생 시 사용자에게 알림을 띄웁니다.
      notify(err.message);
    },
  });

  /** 폼 제출 시 호출되는 핸들러입니다. */
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // `mutate` 함수를 호출하여 `useMutation`에 정의된 `mutationFn`을 실행합니다.
    mutate(profileText);
  };

  // 데이터 로딩 중이거나 저장 중일 때를 나타내는 통합 로딩 상태
  const isLoading = isQueryLoading || isMutationPending;

  // --- 4. UI 렌더링 ---
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
