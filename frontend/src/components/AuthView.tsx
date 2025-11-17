/**
 * @file 사용자 인증(로그인/회원가입)을 위한 UI 컴포넌트입니다.
 * @description 사용자는 이 화면을 통해 아이디와 비밀번호를 입력하여 로그인하거나,
 * 새로운 계정을 생성할 수 있습니다.
 */

import { useState } from "react";
import { z } from "zod";
import { getApiBaseUrl } from "../hooks/useEnvironment";
import { AuthResult } from "../providers/AuthProvider";
import { User } from "../schemas";

/**
 * Zod를 사용한 로그인 폼 데이터 유효성 검사 스키마입니다.
 * - username: 최소 2자 이상이어야 합니다.
 * - password: 최소 4자 이상이어야 합니다.
 */
const loginSchema = z.object({
  username: z.string().min(2),
  password: z.string().min(4),
});

type Props = {
  /**
   * 인증(로그인/회원가입) 성공 시 호출될 콜백 함수입니다.
   * 부모 컴포넌트(App.tsx)로부터 전달받아, 인증 결과를 상위로 전파합니다.
   */
  onSuccess: (result: AuthResult) => void;
};

/**
 * 로그인 및 회원가입 UI를 렌더링하고 관련 로직을 처리하는 메인 컴포넌트입니다.
 */
export default function AuthView({ onSuccess }: Props) {
  // 'login' 또는 'register' 모드를 관리하는 상태
  const [mode, setMode] = useState<"login" | "register">("login");
  // 사용자명, 비밀번호 입력 값을 관리하는 상태
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  // API 요청 중 로딩 상태를 관리하는 상태
  const [loading, setLoading] = useState(false);
  // 에러 메시지를 관리하는 상태
  const [error, setError] = useState<string | null>(null);

  /**
   * 폼 제출(submit) 이벤트를 처리하는 비동기 함수입니다.
   * 로그인 또는 회원가입 API를 호출하고, 그 결과에 따라 상태를 업데이트합니다.
   */
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); // 폼의 기본 제출 동작(페이지 새로고침)을 막습니다.
    setError(null);

    // 1. Zod 스키마를 사용하여 입력 값의 유효성을 검사합니다.
    const parsed = loginSchema.safeParse({ username, password });
    if (!parsed.success) {
      setError("아이디와 비밀번호를 확인해주세요.");
      return;
    }

    setLoading(true);
    try {
      // 2. 'register' 모드일 경우, 먼저 회원가입 API를 호출합니다.
      if (mode === "register") {
        await callApiPostJson("/auth/register", {
          username,
          password,
          permission_groups: ["all_users"], // 기본 권한 그룹 설정
        });
        // 회원가입 성공 후, 자동으로 로그인 절차를 진행합니다.
      }

      // 3. 로그인 API(/auth/token)를 호출하여 액세스 토큰을 발급받습니다.
      const tokenResponse = await callForm("/auth/token", { username, password });

      // 4. 발급받은 토큰을 사용하여 사용자 정보(/auth/me)를 조회합니다.
      const userResponse = await callApiGet<User>(
        "/auth/me",
        tokenResponse.access_token
      );

      // 5. 인증 성공 시, 토큰과 사용자 정보를 부모 컴포넌트로 전달합니다.
      onSuccess({ token: tokenResponse.access_token, user: userResponse });
    } catch (err) {
      // API 요청 실패 시 에러 메시지를 상태에 저장하여 UI에 표시합니다.
      setError(err instanceof Error ? err.message : "알 수 없는 오류");
    } finally {
      // 요청 성공/실패 여부와 관계없이 로딩 상태를 해제합니다.
      setLoading(false);
    }
  }

  return (
    <div className="auth-wrapper">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1>Sentinel Core</h1>
        <p>사내 RAG 콘솔에 로그인하세요.</p>
        <label>
          사용자명
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="alice"
            required
          />
        </label>
        <label>
          비밀번호
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="auth-error">{error}</p>}
        <button type="submit" disabled={loading}>
          {loading ? "처리 중..." : mode === "login" ? "로그인" : "회원가입 후 로그인"}
        </button>
        <p className="auth-mode">
          {mode === "login" ? (
            <>
              계정이 없나요?{" "}
              <button type="button" onClick={() => setMode("register")}>
                회원가입
              </button>
            </>
          ) : (
            <>
              이미 계정이 있나요?{" "}
              <button type="button" onClick={() => setMode("login")}>
                로그인
              </button>
            </>
          )}
        </p>
      </form>
    </div>
  );
}

/**
 * JSON 형식의 데이터를 POST 방식으로 전송하는 API 헬퍼 함수입니다.
 * (주로 회원가입에 사용)
 * @param path API 경로 (예: "/auth/register")
 * @param body 요청 본문에 포함될 JSON 객체
 * @returns API 응답을 JSON으로 파싱한 결과
 */
async function callApiPostJson(path: string, body: unknown) {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`요청 실패 (${res.status})`);
  }
  if (res.status === 204) return null; // No Content 응답 처리
  return res.json();
}

/**
 * GET 방식으로 데이터를 요청하고, 인증 토큰을 헤더에 포함하는 API 헬퍼 함수입니다.
 * (주로 사용자 정보 조회에 사용)
 * @param path API 경로 (예: "/auth/me")
 * @param token 인증에 사용할 JWT 액세스 토큰
 * @returns API 응답을 JSON으로 파싱한 결과 (제네릭 타입 T로 캐스팅)
 */
async function callApiGet<T = any>(path: string, token: string): Promise<T> {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}${path}`, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new Error(`/me 요청 실패 (${res.status})`);
  }
  return res.json() as T;
}

/**
 * 'application/x-www-form-urlencoded' 형식으로 데이터를 POST 전송하는 API 헬퍼 함수입니다.
 * OAuth 2.0의 토큰 요청 형식에 따라, 로그인 API 호출에 사용됩니다.
 * @param path API 경로 (예: "/auth/token")
 * @param body 사용자 아이디와 비밀번호
 * @returns API 응답을 JSON으로 파싱한 결과 (액세스 토큰 포함)
 */
async function callForm(path: string, body: { username: string; password: string }) {
  const form = new URLSearchParams();
  form.set("username", body.username);
  form.set("password", body.password);
  const base = getApiBaseUrl();
  const res = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
  });
  if (!res.ok) {
    throw new Error("로그인에 실패했습니다.");
  }
  return res.json();
}
