/**
 * @file 프론트엔드와 백엔드 API 간의 데이터 계약(Data Contract)을 TypeScript 타입으로 정의합니다.
 * @description 이 파일에 정의된 타입들은 API 통신의 요청(Request) 및 응답(Response) 객체의
 * 구조를 명시하여, 개발 과정에서의 타입 안정성을 보장하고 잠재적인 오류를 방지합니다.
 * 백엔드 API의 Pydantic 스키마와 일관성을 유지하는 것이 중요합니다.
 */

/**
 * 백엔드 `/admin/approve_promotion` API의 요청 본문(Request Body) 스키마입니다.
 * 임시 세션 첨부파일을 영구적인 지식 베이스(KB) 문서로 승격시킬 때 사용됩니다.
 */
export type PromotionApprovalRequest = {
  /**
   * 영구 지식 베이스에 저장될 문서의 새로운 고유 ID.
   */
  kb_doc_id: string;
  /**
   * 이 문서에 접근할 수 있는 사용자 권한 그룹의 목록입니다.
   */
  permission_groups: string[];
};

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
   * 사용자가 속한 권한 그룹의 목록. RAG 검색 등에서 데이터 접근 제어에 사용됩니다.
   */
  permission_groups: string[];
  /**
   * 계정이 생성된 시간 (ISO 8601 형식의 문자열).
   */
  created_at: string;
};