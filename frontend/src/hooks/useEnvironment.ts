/**
 * @file 프론트엔드 애플리케이션의 환경 변수를 관리하는 유틸리티 파일입니다.
 * @description 이 파일은 Vite에서 제공하는 환경 변수 시스템(`import.meta.env`)을 사용하여
 * 빌드 시점 또는 런타임에 주입된 환경 변수를 안전하게 읽어오는 함수를 제공합니다.
 *
 * @note 파일 이름은 `useEnvironment.ts`이지만, React 훅(Hook)을 포함하고 있지는 않습니다.
 * 이름은 관례상 환경 관련 로직을 모아두는 파일을 의미합니다.
 */

const DEFAULT_API = "/api";

/**
 * 백엔드 API의 기본 URL을 반환합니다.
 *
 * 이 함수는 Vite 환경 변수인 `VITE_API_BASE_URL`을 먼저 확인합니다.
 * 만약 이 변수가 설정되어 있지 않다면, 기본값으로 `/api`를 사용합니다.
 * `/api`는 상대 경로이므로, 프론트엔드와 동일한 도메인에서 API를 서빙할 때
 * Nginx나 다른 리버스 프록시를 통해 라우팅하는 일반적인 구성에 적합합니다.
 *
 * @returns {string} API의 기본 URL
 */
export function getApiBaseUrl() {
  // `import.meta.env`는 Vite가 제공하는 기능으로, `.env` 파일에 정의된
  // `VITE_` 접두사가 붙은 환경 변수들을 담고 있는 객체입니다.
  const envVar = (import.meta as any).env?.VITE_API_BASE_URL;
  
  // 환경 변수가 설정되지 않았을 경우, 개발자에게 경고 메시지를 표시합니다.
  if (!envVar && typeof window !== "undefined") {
    console.warn(
      "VITE_API_BASE_URL이 정의되지 않아 기본값을 사용합니다. (브라우저)",
    );
  }
  
  // 환경 변수가 있으면 그 값을, 없으면 기본값 `/api`를 반환합니다.
  return envVar || DEFAULT_API;
}
