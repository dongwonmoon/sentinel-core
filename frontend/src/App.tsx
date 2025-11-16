/**
 * @file 애플리케이션의 루트 컴포넌트 파일입니다.
 * @description 이 파일은 앱의 전체적인 구조를 정의하며, 인증 상태에 따라
 * 로그인 화면(`AuthView`) 또는 메인 채팅 화면(`ChatLayout`)을 렌더링합니다.
 * 또한, 앱 전체에서 사용될 주요 컨텍스트 프로바이더(`AuthProvider`, `QueryClientProvider`)를 설정합니다.
 */

import { useMemo } from "react";
import {
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import AuthView from "./components/AuthView";
import ChatLayout from "./components/ChatLayout";
import { AuthProvider, useAuth } from "./providers/AuthProvider";

/**
 * TanStack Query(React Query) 클라이언트 인스턴스를 생성하고 설정합니다.
 * @returns {QueryClient} 설정이 완료된 QueryClient 인스턴스.
 */
function createClient() {
  return new QueryClient({
    queryCache: new QueryCache(),
    defaultOptions: {
      queries: {
        // 데이터 페칭 실패 시, 자동으로 1번만 재시도합니다.
        retry: 1,
        // 사용자가 브라우저 창을 다시 포커스했을 때 자동으로 데이터를 다시 가져오지 않도록 설정합니다.
        // 이는 불필요한 API 호출을 줄여줍니다.
        refetchOnWindowFocus: false,
      },
    },
  });
}

/**
 * 애플리케이션의 최상위 진입 컴포넌트입니다.
 * `AuthProvider`로 하위 컴포넌트들을 감싸, 앱 전체에서 인증 관련 상태 및 함수에
 * 접근할 수 있도록 합니다.
 */
export default function App() {
  return (
    <AuthProvider>
      <AuthenticatedApp />
    </AuthProvider>
  );
}

/**
 * 인증 상태에 따라 적절한 UI를 렌더링하는 컴포넌트입니다.
 * 일종의 '게이트키퍼' 역할을 수행합니다.
 */
function AuthenticatedApp() {
  // AuthProvider로부터 현재 사용자 정보와 로그인 함수를 가져옵니다.
  const { user, signIn } = useAuth();

  // QueryClient 인스턴스를 생성합니다.
  // useMemo를 사용하여 컴포넌트가 리렌더링될 때마다 QueryClient가 재생성되는 것을 방지합니다.
  // 이는 애플리케이션의 데이터 캐시가 의도치 않게 초기화되는 것을 막아줍니다.
  const client = useMemo(() => createClient(), []);

  // 사용자가 인증되지 않은 경우(user 객체가 없음), 로그인 화면을 보여줍니다.
  // onSuccess 콜백으로 signIn 함수를 전달하여, 로그인 성공 시 상태를 업데이트하고
  // 이 컴포넌트를 리렌더링하게 합니다.
  if (!user) {
    return <AuthView onSuccess={signIn} />;
  }

  // 사용자가 인증된 경우, 메인 채팅 레이아웃을 렌더링합니다.
  // `QueryClientProvider`로 감싸 하위의 모든 컴포넌트(ChatLayout 등)가
  // 위에서 생성한 client 인스턴스를 사용하여 데이터 페칭 및 캐싱을 할 수 있도록 합니다.
  return (
    <QueryClientProvider client={client}>
      <ChatLayout />
    </QueryClientProvider>
  );
}
