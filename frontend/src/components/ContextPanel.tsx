import { useMemo, useRef, useState, useEffect } from "react";
import { notify } from "./NotificationHost";
import { apiRequest } from "../lib/apiClient";
import { useAuth } from "../providers/AuthProvider";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { SessionAttachment } from "../hooks/useChatSession";
import Modal from "./Modal";
import { PromotionApprovalRequest } from "../schemas";
import PanelTabs from "./PanelTabs";
import { useTaskPolling, TaskStatusResponse } from "../hooks/useTaskPolling";

// (거버넌스) 관리자 승인 모달
function ApprovalModal({
  attachment,
  onClose,
  onSubmit,
}: {
  attachment: SessionAttachment;
  onClose: () => void;
  onSubmit: (data: PromotionApprovalRequest) => void;
}) {
  // 사용자가 제안한 ID를 기본값으로 사용
  const defaultKbId = attachment.pending_review_metadata?.suggested_kb_doc_id || 
                      (attachment.filename.split(".").slice(0, -1).join(".") || attachment.filename);
                      
  const [kbDocId, setKbDocId] = useState(defaultKbId);
  const [permissionGroups, setPermissionGroups] = useState("all_users");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!kbDocId.trim() || !permissionGroups.trim()) {
      notify("KB 문서 ID와 권한 그룹을 입력해야 합니다.");
      return;
    }
    onSubmit({
      kb_doc_id: kbDocId.trim(),
      permission_groups: permissionGroups.split(",").map(g => g.trim()),
    });
  };
  
  return (
    <Modal onClose={onClose} width="min(600px, 90vw)">
      <form onSubmit={handleSubmit} className="panel-form" style={{ gap: '1rem' }}>
        <h3>지식 베이스(KB) 승인</h3>
        <p className="muted">
          <b>{attachment.filename}</b> (요청자: {attachment.user_id || '알 수 없음'})
        </p>
        <p className="muted" style={{ borderLeft: '3px solid var(--color-primary)', paddingLeft: '1rem' }}>
          <b>요청자 메모:</b> {attachment.pending_review_metadata?.note_to_admin || "(없음)"}
        </p>
        <label>
          영구 KB 문서 ID (필수)
          <input
            value={kbDocId}
            onChange={(e) => setKbDocId(e.target.value)}
            required
          />
        </label>
        <label>
          권한 그룹 (필수, 쉼표로 구분)
          <input
            value={permissionGroups}
            onChange={(e) => setPermissionGroups(e.target.value)}
            placeholder="all_users, it, hr"
            required
          />
        </label>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem' }}>
          <button type="button" className="ghost" onClick={onClose}>취소</button>
          <button type="submit" className="primary">최종 승인 및 발행</button>
        </div>
      </form>
    </Modal>
  );
}

// (거버넌스) 관리자용 승인 패널
function AdminReviewPanel({ token }: { token: string }) {
  const queryClient = useQueryClient();
  const [selectedAttachment, setSelectedAttachment] = useState<SessionAttachment | null>(null);

  // 1. 승인 대기 목록 조회
  const { data: pendingAttachments, isLoading } = useQuery({
    queryKey: ["pendingAttachments"],
    queryFn: () => 
      apiRequest<SessionAttachment[]>("/admin/pending_attachments", { token }),
    enabled: !!token,
  });
  
  // 2. 승인/반려 Mutation
  const { mutate: approveMutate, isPending: isApproving } = useMutation({
    mutationFn: ({ attachmentId, data }: { attachmentId: number, data: PromotionApprovalRequest }) =>
      apiRequest<{ task_id: string }>(`/admin/approve_promotion/${attachmentId}`, {
        method: 'POST',
        token,
        json: data,
        errorMessage: "승인 실패"
      }),
    onSuccess: (data: { task_id: string }) => {
      notify("KB 승인 완료. 영구 지식 복사 작업을 시작합니다.");
      queryClient.invalidateQueries({ queryKey: ["pendingAttachments"] });
      // (선택적) 이 task_id로 폴링하여 'promoted' 상태 확인
      setSelectedAttachment(null);
    },
    onError: (err) => notify(err.message),
  });
  
  const { mutate: rejectMutate, isPending: isRejecting } = useMutation({
     mutationFn: (attachmentId: number) =>
      apiRequest(`/admin/reject_promotion/${attachmentId}`, {
        method: 'POST',
        token,
        errorMessage: "반려 실패"
      }),
    onSuccess: () => {
      notify("요청이 반려되었습니다.");
      queryClient.invalidateQueries({ queryKey: ["pendingAttachments"] });
    },
    onError: (err) => notify(err.message),
  });
  
  const isPending = isApproving || isRejecting;

  return (
    <section>
      <h4>KB 등록 승인 대기</h4>
      {isLoading && <p className="muted">로딩 중...</p>}
      <div className="doc-list">
        {!isLoading && pendingAttachments?.length === 0 && <p className="muted">승인 대기 중인 문서가 없습니다.</p>}
        {pendingAttachments?.map(att => (
          <div key={att.attachment_id} className="doc-item">
            <div style={{ flex: 1 }}>
              <p style={{ margin: 0, fontSize: '0.9rem' }}>{att.filename}</p>
              <small className="muted">요청 ID: {att.attachment_id}</small>
            </div>
            <button className="ghost" onClick={() => rejectMutate(att.attachment_id)} disabled={isPending}>반려</button>
            <button onClick={() => setSelectedAttachment(att)} disabled={isPending}>검토/승인</button>
          </div>
        ))}
      </div>
      
      {selectedAttachment && (
        <ApprovalModal 
          attachment={selectedAttachment}
          onClose={() => setSelectedAttachment(null)}
          onSubmit={(data) => approveMutate({ attachmentId: selectedAttachment.attachment_id, data })}
        />
      )}
    </section>
  );
}

type Props = {
  documents: { id: string; name: string }[];
  onRefresh: () => void;
  onSelectDoc: (id: string | null) => void;
};

export default function ContextPanel({ documents, onRefresh, onSelectDoc }: Props) {
  const { user, token } = useAuth();
  const [docSearch, setDocSearch] = useState("");
  if (!token || !user) return null;

  const isAdmin = useMemo(() => user.permission_groups.includes("admin"), [user]);
  const [activeTab, setActiveTab] = useState("kb_search");

  async function handleDelete(docId: string) {
    if (!confirm("정말 삭제하시겠습니까?")) return;

    if (!token) {
      notify("인증 정보가 없습니다. 다시 로그인해주세요.");
      return;
    }
    try {
      await apiRequest("/documents", {
        method: "DELETE",
        token: token,
        json: { doc_id_or_prefix: docId },
        errorMessage: "삭제 실패",
      });
      notify("문서를 삭제했습니다.");
      onRefresh();
      onSelectDoc(null);
    } catch (err) {
      notify(err instanceof Error ? err.message : "삭제 중 오류");
    }
  }

  const filteredDocs = useMemo(() => {
    const query = docSearch.trim().toLowerCase();
    if (!query) return documents;
    return documents.filter((doc) =>
      doc.name.toLowerCase().includes(query) || doc.id.toLowerCase().includes(query),
    );
  }, [documents, docSearch]);

  const TABS = [
    { id: "kb_search", label: "KB 검색/필터" },
  ];
  if (isAdmin) {
    TABS.push({ id: "kb_admin", label: "KB 승인 관리" });
  }

  return (
    <aside className="context-panel">
      {/* [신규] 탭 UI */}
      {TABS.length > 1 && (
        <PanelTabs 
          tabs={TABS} 
          activeId={activeTab} 
          onChange={setActiveTab} 
        />
      )}
      <div className={`fade-in-out ${activeTab === "kb_search" ? "active" : ""}`}>
        <section>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3>영구 지식 베이스(KB)</h3>
            <button className="ghost" onClick={onRefresh}>
              새로고침
            </button>
          </div>
          <p className="muted" style={{ marginTop: "-0.4rem", marginBottom: "0.5rem" }}>
            총 {documents.length}건 · {filteredDocs.length}건 표시 중
          </p>
          <input
            type="search"
            placeholder="이름 또는 ID로 필터링"
            value={docSearch || ''}
            onChange={(e) => setDocSearch(e.target.value)}
            style={{ marginBottom: "0.75rem" }}
          />
          <div className="doc-list">
            {filteredDocs.length === 0 && <p className="muted">조건에 맞는 문서가 없습니다.</p>}
            {filteredDocs.map((doc) => (
              <div key={doc.id} className="doc-item">
                <button onClick={() => onSelectDoc(doc.id)}>{doc.name}</button>
                <button className="ghost" onClick={() => handleDelete(doc.id)}>
                  삭제
                </button>
              </div>
            ))}
          </div>
        </section>
      </div>

      {isAdmin && (
        <div className={`fade-in-out ${activeTab === "kb_admin" ? "active" : ""}`}>
          <AdminReviewPanel token={token} />
        </div>
      )}      
    </aside>
  );
}

function extractResultMessage(
  response: TaskStatusResponse,
  fallback: string,
) {
  if (!response.result) return fallback;
  if (typeof response.result === "string") return response.result;
  return (response.result as any).message ?? fallback;
}
