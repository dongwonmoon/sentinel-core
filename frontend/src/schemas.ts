/**
 * 백엔드 /admin/approve_promotion API의 요청 본문 스키마
 */
export type PromotionApprovalRequest = {
  kb_doc_id: string;
  permission_groups: string[];
};

/**
 * 백엔드 /api/auth/me API의 응답 스키마
 */
export type User = {
  user_id: number;
  username: string;
  is_active: boolean;
  permission_groups: string[];
  created_at: string; // ISO 문자열
};