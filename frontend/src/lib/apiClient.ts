/**
 * @file 백엔드 API와의 통신을 중앙에서 관리하는 API 클라이언트입니다.
 * @description
 * 이 파일은 네이티브 `fetch` API를 감싸는 `apiRequest` 함수를 제공합니다.
 * API 클라이언트를 중앙화하면 다음과 같은 이점이 있습니다:
 * - **일관된 인증 처리**: 모든 요청에 JWT 토큰을 쉽게 추가할 수 있습니다.
 * - **표준화된 에러 처리**: 모든 API 실패(non-2xx 응답)를 동일한 방식으로 처리합니다.
 * - **간소화된 요청**: `Content-Type` 헤더 설정이나 `JSON.stringify` 같은 반복 작업을 자동화합니다.
 * - **유지보수 용이성**: API 관련 로직 변경이 필요할 때, 이 파일만 수정하면 됩니다.
 */

import { getApiBaseUrl } from "../hooks/useEnvironment";

// 환경에 따라 동적으로 API 기본 URL을 가져옵니다. (예: http://localhost:8000)
const API_BASE = getApiBaseUrl();

/**
 * `fetch` 요청에 사용될 확장된 옵션 타입입니다.
 */
type ApiRequestOptions = Omit<RequestInit, "body" | "headers"> & {
  headers?: HeadersInit;
  body?: BodyInit;
  /**
   * 인증이 필요한 요청에 사용될 JWT 토큰입니다.
   */
  token?: string;
  /**
   * JSON 페이로드를 보내기 위한 편의 옵션입니다.
   * 이 옵션을 사용하면 `body`가 자동으로 `JSON.stringify`되고,
   * 'Content-Type' 헤더가 'application/json'으로 설정됩니다.
   * `body` 옵션과 함께 사용할 수 없습니다.
   */
  json?: Record<string, unknown>;
  /**
   * 요청 실패 시 표시할 기본 에러 메시지입니다.
   */
  errorMessage?: string;
};

/**
 * 애플리케이션 전체에서 사용되는 `fetch` API의 중앙화된 래퍼(wrapper) 함수입니다.
 * 이 함수를 통해 API 요청의 인증(Authorization), 헤더 설정, 에러 처리 등을
 * 일관된 방식으로 관리할 수 있습니다.
 *
 * @template T - API 응답 본문의 예상 타입. 기본값은 `void`입니다. 제네릭을 통해 타입스크립트의 타입 안전성을 확보합니다.
 * @param {string} path - API의 기본 URL(API_BASE) 뒤에 붙는 경로 (예: '/chat/history').
 * @param {ApiRequestOptions} [options={}] - `fetch` 옵션을 확장한 커스텀 옵션 객체.
 * @returns {Promise<T>} - API 응답을 JSON으로 파싱한 결과.
 * @throws {Error} - 네트워크 에러 또는 API가 2xx가 아닌 상태 코드를 반환했을 때 발생합니다.
 */
export async function apiRequest<T = void>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  // 1. 옵션 분리: 커스텀 옵션(token, json 등)과 표준 fetch 옵션을 분리합니다.
  const { token, json, errorMessage, headers, body, ...rest } = options;
  const finalHeaders = new Headers(headers);

  // 2. 인증 헤더 설정: 토큰이 제공되면, Authorization 헤더를 'Bearer' 토큰으로 설정합니다.
  //    이 로직 덕분에 모든 인증 요청을 동일한 방식으로 처리할 수 있습니다.
  if (token) {
    finalHeaders.set("Authorization", `Bearer ${token}`);
  }

  const init: RequestInit = {
    ...rest,
    headers: finalHeaders,
  };

  // 3. Body 및 Content-Type 설정: 'json' 옵션이 있으면, body를 JSON 문자열로 변환하고
  //    Content-Type 헤더를 'application/json'으로 자동 설정합니다.
  if (json) {
    finalHeaders.set("Content-Type", "application/json");
    init.body = JSON.stringify(json);
  } else if (body) {
    // 'json'이 아닌 다른 body(예: FormData)가 있으면 그대로 사용합니다.
    init.body = body;
  }

  // 4. API 요청 실행
  const response = await fetch(`${API_BASE}${path}`, init);

  // 5. 에러 처리: 응답 상태가 'ok' (200-299)가 아니면 에러를 발생시킵니다.
  //    이렇게 하면 React Query와 같은 라이브러리에서 `isError` 상태를 쉽게 관리할 수 있습니다.
  if (!response.ok) {
    // TODO: 서버에서 내려주는 구체적인 에러 메시지(예: response.json()의 detail)를 파싱하여
    //       더 유용한 에러 메시지를 제공하도록 개선할 수 있습니다.
    // const errorData = await response.json().catch(() => null);
    // const message = errorData?.detail || errorMessage;
    throw new Error(errorMessage ?? `요청에 실패했습니다. (상태: ${response.status})`);
  }

  // 6. 204 No Content 처리: 응답 본문이 없는 성공적인 요청(예: DELETE)의 경우,
  //    .json()을 호출하면 에러가 발생하므로, undefined를 즉시 반환합니다.
  if (response.status === 204) {
    return undefined as T;
  }

  // 7. 성공 응답 처리: 성공적인 응답의 경우, JSON 본문을 파싱하여 반환합니다.
  return (await response.json()) as T;
}
