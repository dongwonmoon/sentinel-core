/**
 * @file 프론트엔드와 백엔드 API 간의 데이터 계약(Data Contract)을 TypeScript 타입으로 정의합니다.
 * @description 이 파일에 정의된 타입들은 API 통신의 요청(Request) 및 응답(Response) 객체의
 * 구조를 명시하여, 개발 과정에서의 타입 안정성을 보장하고 잠재적인 오류를 방지합니다.
 * 백엔드 API의 Pydantic 스키마와 일관성을 유지하는 것이 중요합니다.
 */

/**
 * 백엔드 `/api/auth/me` API의 응답(Response) 스키마입니다.
 * 현재 로그인된 사용자의 상세 정보를 나타냅니다.
 */
export type User = {
  /**
   * 사용자의 고유 ID.
   */
  user_id: number;
  /**
   * 사용자의 로그인 이름.
   */
  username: string;
  /**
   * 계정의 활성화 상태. `false`일 경우 로그인이 제한될 수 있습니다.
   */
  is_active: boolean;
  /**
   * 계정이 생성된 시간 (ISO 8601 형식의 문자열).
   */
  created_at: string;
};