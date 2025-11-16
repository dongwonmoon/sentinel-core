import { useMemo, useState } from "react";
import MessageList from "./MessageList";
import Composer from "./Composer";
import { Message, SessionAttachment } from "../hooks/useChatSession";
import Modal from "./Modal";
import { notify } from "./NotificationHost";

function PromotionModal({
  attachment,
  onClose,
  onSubmit,
}: {
  attachment: SessionAttachment;
  onClose: () => void;
  onSubmit: (metadata: { suggested_kb_doc_id: string; note_to_admin: string }) => void;
}) {
  const [kbDocId, setKbDocId] = useState(
    // 파일 확장자 제거 (예: hr_policy.pdf -> hr_policy)
    attachment.filename.split(".").slice(0, -1).join(".") || attachment.filename
  );
  const [note, setNote] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!kbDocId.trim()) {
      notify("KB 문서 ID를 입력해야 합니다.");
      return;
    }
    onSubmit({ suggested_kb_doc_id: kbDocId.trim(), note_to_admin: note.trim() });
    onClose();
  };
  
  return (
    <Modal onClose={onClose} width="min(600px, 90vw)">
      <form onSubmit={handleSubmit} className="panel-form" style={{ gap: '1rem' }}>
        <h3>지식 베이스(KB) 등록 요청</h3>
        <p className="muted">
          '<b>{attachment.filename}</b>' 파일을 전사 영구 지식으로 등록 요청합니다.
          <br/>
          관리자가 승인하면 모든 직원이 이 문서를 검색할 수 있습니다.
        </p>
        <label>
          영구 KB 문서 ID (필수)
          <input
            value={kbDocId}
            onChange={(e) => setKbDocId(e.target.value)}
            placeholder="예: hr-policy-v3 (고유해야 함)"
            required
          />
        </label>
        <label>
          관리자에게 남기는 메모 (선택)
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="예: v2 문서를 대체합니다. 'hr' 그룹으로 지정해주세요."
            rows={3}
          />
        </label>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem' }}>
          <button type="button" className="ghost" onClick={onClose}>취소</button>
          <button type="submit" className="primary">요청 제출</button>
        </div>
      </form>
    </Modal>
  );
}

type Props = {
  documentOptions: { id: string; name: string }[];
  selectedDoc: string | null;
  onDocChange: (value: string | null) => void;
  messages: Message[];
  loading: boolean;
  sendMessage: (payload: { query: string; docFilter?: string }) => Promise<void>;
  attachments: SessionAttachment[];
  handleAttachFile: (file: File) => Promise<void>;
  handleRequestPromotion: (
    attachmentId: number,
    metadata: { suggested_kb_doc_id: string; note_to_admin: string }
  ) => Promise<void>;
};

export default function ChatWindow({
  documentOptions,
  selectedDoc,
  onDocChange,
  messages,
  loading,
  sendMessage,
  attachments,
  handleAttachFile,
  handleRequestPromotion,
}: Props) {
  // const session = useChatSession(auth.token, selectedDoc);
  const attachmentStatus = useMemo(() => {
    if (!attachments || attachments.length === 0) return null;
    
    const indexingCount = attachments.filter(a => a.status === 'indexing').length;
    const readyCount = attachments.filter(a => a.status === 'temporary').length;
    
    let statusText = `첨부파일 ${readyCount}개 사용 중`;
    if (indexingCount > 0) {
      statusText += ` (${indexingCount}개 인덱싱 중...)`;
    }
    return statusText;
  }, [attachments]);
  const [promotingAttachment, setPromotingAttachment] = useState<SessionAttachment | null>(null);

  return (
    <section className="chat-window">
      <header className="chat-header">
        <div>
          <h2>대화</h2>
          <p className="muted">
            [영구 KB 필터: {selectedDoc ? selectedDoc : "모든 문서"}]
          </p>
          
          {/* (거버넌스) 임시 첨부파일 상태 표시 UI */}
          {attachments.length > 0 && (
            <div className="doc-list" style={{ gap: '0.25rem', marginTop: '0.5rem' }}>
              {attachments.map(att => (
                <div key={att.attachment_id || att.task_id} className="doc-item" style={{ padding: '0.4rem 0.6rem' }}>
                  <span style={{ fontSize: '0.85rem' }}>📎 {att.filename}</span>
                  {att.status === 'indexing' && <small className="muted"> (인덱싱 중...)</small>}
                  {att.status === 'failed' && <small style={{ color: '#f87171' }}> (실패)</small>}
                  {att.status === 'temporary' && (
                    <button 
                      className="ghost" 
                      style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}
                      onClick={() => setPromotingAttachment(att)}
                    >
                      [+] KB에 추가
                    </button>
                  )}
                  {att.status === 'pending_review' && <small className="muted"> (승인 대기중)</small>}
                  {att.status === 'promoted' && <small style={{ color: '#10b981' }}> (KB 등록됨)</small>}
                </div>
              ))}
            </div>
          )}
        </div>
        <select
          value={selectedDoc ?? ""}
          onChange={(e) => onDocChange(e.target.value || null)}
        >
          <option value="">모든 영구 문서</option>
          {documentOptions.map((doc) => (
            <option key={doc.id} value={doc.id}>
              {doc.name}
            </option>
          ))}
        </select>
      </header>
      <MessageList messages={messages} sendMessage={sendMessage} />
      <Composer
        disabled={loading}
        onSend={(text) =>
          sendMessage({
            query: text,
            docFilter: selectedDoc ?? undefined,
          })
        }
        onAttachFile={handleAttachFile} // 핸들러 연결
      />
      {promotingAttachment && (
        <PromotionModal
          attachment={promotingAttachment}
          onClose={() => setPromotingAttachment(null)}
          onSubmit={(metadata) => 
            handleRequestPromotion(promotingAttachment.attachment_id, metadata)
          }
        />
      )}
    </section>
  );
}
