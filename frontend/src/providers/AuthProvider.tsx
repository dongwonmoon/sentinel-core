/**
 * @file React 컨텍스트(Context)를 사용하여 앱 전체의 인증 상태를 관리하는 프로바이더(Provider)입니다.
 * @description 이 파일은 다음 세 가지 주요 요소를 제공합니다:
 * 1. `AuthContext`: 인증 상태(사용자 정보, 토큰)와 관련 함수(로그인, 로그아웃)를 담는 컨텍스트 객체.
 * 2. `AuthProvider`: `AuthContext`를 하위 컴포넌트들에게 제공하는 래퍼(wrapper) 컴포넌트.
 *    실제 상태 관리, `localStorage` 연동 로직을 포함합니다.
 * 3. `useAuth`: 하위 컴포넌트에서 `AuthContext`의 값에 쉽게 접근할 수 있도록 하는 커스텀 훅.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  ReactNode,
} from "react";
import { User } from "../schemas";

/** 로그인 성공 시 반환되는 데이터의 구조를 정의합니다. */
export type AuthResult = {
  /** 서버로부터 발급받은 JWT 액세스 토큰 */
  token: string;
  /** 현재 로그인한 사용자의 상세 정보 */
  user: User;
};

/** `AuthContext`가 하위 컴포넌트에 제공하는 값의 타입을 정의합니다. */
type AuthContextValue = {
  /** 현재 로그인된 사용자 객체. 비로그인 상태일 경우 `null`. */
  user: User | null;
  /** 현재 JWT 액세스 토큰. 비로그인 상태일 경우 `null`. */
  token: string | null;
  /** 로그인 상태를 업데이트하는 함수 */
  signIn: (next: AuthResult) => void;
  /** 로그아웃을 처리하는 함수 */
  signOut: () => void;
};

/**
 * 인증 상태를 담을 React 컨텍스트 객체입니다.
 * 초기값은 `null`이며, `AuthProvider`를 통해 실제 값이 주입됩니다.
 */
const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * 인증 컨텍스트를 하위 컴포넌트 트리에 제공하는 프로바이더 컴포넌트입니다.
 * 앱의 루트 근처에서 모든 컴포넌트를 감싸야 합니다.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  // --- 상태 관리 및 로컬 스토리지 연동 ---

  // `token` 상태를 `localStorage`에서 초기화합니다.
  // `useState`에 함수를 전달하면, 이 함수는 컴포넌트가 처음 렌더링될 때 한 번만 실행됩니다.
  // 이를 통해 페이지를 새로고침해도 로그인 상태가 유지됩니다.
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem("sentinel_token")
  );

  // `user` 상태를 `localStorage`에서 초기화합니다.
  const [user, setUser] = useState<User | null>(() => {
    const userJson = localStorage.getItem("sentinel_user");
    if (!userJson) return null;
    try {
      // JSON 문자열을 파싱하여 사용자 객체로 복원합니다.
      return JSON.parse(userJson) as User;
    } catch {
      // 파싱 실패 시 (예: 데이터 손상) null을 반환합니다.
      return null;
    }
  });

  // --- 인증 관련 함수 ---

  // `signIn` 함수: 로그인 시 호출되어 상태와 `localStorage`를 업데이트합니다.
  // `useCallback`으로 감싸, 불필요한 리렌더링을 방지합니다.
  const signIn = useCallback((next: AuthResult) => {
    localStorage.setItem("sentinel_token", next.token);
    localStorage.setItem("sentinel_user", JSON.stringify(next.user));
    setToken(next.token);
    setUser(next.user);
  }, []);

  // `signOut` 함수: 로그아웃 시 호출되어 상태와 `localStorage`를 초기화합니다.
  const signOut = useCallback(() => {
    localStorage.removeItem("sentinel_token");
    localStorage.removeItem("sentinel_user");
    setToken(null);
    setUser(null);
  }, []);

  // --- 컨텍스트 값 최적화 ---

  // `useMemo`를 사용하여 컨텍스트 값을 메모이제이션합니다.
  // `user`, `token`, `signIn`, `signOut` 중 하나라도 변경되지 않으면,
  // `value` 객체는 재생성되지 않습니다. 이는 컨텍스트를 사용하는 하위 컴포넌트들의
  // 불필요한 리렌더링을 막아 성능을 최적화하는 중요한 패턴입니다.
  const value = useMemo(
    () => ({
      user,
      token,
      signIn,
      signOut,
    }),
    [user, token, signIn, signOut],
  );

  // `AuthContext.Provider`를 통해 계산된 `value`를 하위 컴포넌트들에게 전달합니다.
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * `AuthContext`에 쉽게 접근하기 위한 커스텀 훅입니다.
 * 컴포넌트에서 `useContext(AuthContext)`를 직접 사용하는 대신 이 훅을 사용합니다.
 * @throws {Error} `AuthProvider` 외부에서 사용될 경우 에러를 발생시킵니다.
 * @returns {AuthContextValue} 현재 인증 컨텍스트 값.
 */
export function useAuth() {
  const ctx = useContext(AuthContext);
  // 컨텍스트 값이 null인지 확인하여, `AuthProvider`의 자식 컴포넌트에서만
  // 이 훅을 사용하도록 강제합니다. 이는 개발자의 실수를 방지하는 안전장치입니다.
  if (!ctx) {
    throw new Error("useAuth는 AuthProvider 안에서만 사용 가능합니다.");
  }
  return ctx;
}
