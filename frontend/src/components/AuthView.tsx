import { useState } from "react";
import { z } from "zod";
import { getApiBaseUrl } from "../hooks/useEnvironment";
import { AuthResult } from "../providers/AuthProvider";

const loginSchema = z.object({
  username: z.string().min(2),
  password: z.string().min(4),
});

type Props = {
  onSuccess: (result: AuthResult) => void;
};

export default function AuthView({ onSuccess }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const parsed = loginSchema.safeParse({ username, password });
    if (!parsed.success) {
      setError("아이디와 비밀번호를 확인해주세요.");
      return;
    }
    setLoading(true);
    try {
      if (mode === "register") {
        await callApi("/auth/register", {
          username,
          password,
          permission_groups: ["all_users"],
        });
      }
      const tokenResponse = await callForm("/auth/token", { username, password });
      onSuccess({ token: tokenResponse.access_token, username });
    } catch (err) {
      setError(err instanceof Error ? err.message : "알 수 없는 오류");
    } finally {
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

async function callApi(path: string, body: unknown) {
  const base = getApiBaseUrl();
  const res = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`요청 실패 (${res.status})`);
  }
  if (res.status === 204) return null;
  return res.json();
}

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
