import { useMemo, useState } from "react";
import MessageList from "./MessageList";
import Composer from "./Composer";
import { Message, SessionAttachment } from "../hooks/useChatSession";
import Modal from "./Modal";
import { notify } from "./NotificationHost";

/**
 * 세션에 임시로 첨부된 파일을 영구 지식 베이스(KB)로 등록 요청하는 모달 컴포넌트입니다.
 * @param attachment - 승격 요청할 첨부 파일 정보.
 * @param onClose - 모달을 닫는 함수.
 * @param onSubmit - '요청 제출' 시 호출될 함수.
 */
function PromotionModal({
  attachment,
  onClose,
  onSubmit,
}: {
  attachment: SessionAttachment;
  onClose: () => void;
  onSubmit: (metadata: { suggested_kb_doc_id: string; note_to_admin: string }) => void;
}) {
  // 제안할 KB 문서 ID의 초기값으로 파일명(확장자 제외)을 사용합니다.
  const [kbDocId, setKbDocId] = useState(
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
  // 영구 KB 문서 필터링을 위한 옵션 목록
  documentOptions: { id: string; name: string }[];
  // 현재 선택된 영구 KB 문서 필터
  selectedDoc: string | null;
  // 영구 KB 문서 필터 변경 시 호출될 콜백 함수
  onDocChange: (value: string | null) => void;
  // 화면에 표시될 메시지 목록
  messages: Message[];
  // AI가 답변을 생성 중인지 여부 (로딩 상태)
  loading: boolean;
  // 사용자가 새 메시지를 보낼 때 호출될 함수
  sendMessage: (payload: { query: string; docFilter?: string }) => Promise<void>;
  // 현재 세션에 첨부된 임시 파일 목록
  attachments: SessionAttachment[];
  // 파일 첨부 시 호출될 함수
  handleAttachFile: (file: File) => Promise<void>;
  // 임시 파일의 KB 등록 요청 시 호출될 함수
  handleRequestPromotion: (
    attachmentId: number,
    metadata: { suggested_kb_doc_id: string; note_to_admin: string }
  ) => Promise<void>;
};

/**
 * 채팅 인터페이스의 메인 컨테이너 컴포넌트입니다.
 * 헤더, 메시지 목록, 메시지 입력창(Composer)으로 구성됩니다.
 * 상위 컴포넌트(App.tsx)로부터 상태와 로직을 props로 전달받아 UI를 렌더링하는 역할을 합니다.
 */
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
  // KB 등록 요청 모달을 띄울 첨부 파일 정보를 담는 상태
  const [promotingAttachment, setPromotingAttachment] = useState<SessionAttachment | null>(null);

  return (
    <section className="chat-window">
      {/* 채팅창 헤더: 제목, 영구 KB 필터, 임시 첨부파일 목록 표시 */}
      <header className="chat-header">
        <div>
          <h2>대화</h2>
          <p className="muted">
            [영구 KB 필터: {selectedDoc ? documentOptions.find(d => d.id === selectedDoc)?.name : "모든 문서"}]
          </p>
          
          {/* 현재 세션에 첨부된 임시 파일 목록을 렌더링 */}
          {attachments.length > 0 && (
            <div className="doc-list" style={{ gap: '0.25rem', marginTop: '0.5rem' }}>
              {attachments.map(att => (
                <div key={att.attachment_id || att.task_id} className="doc-item" style={{ padding: '0.4rem 0.6rem' }}>
                  <span style={{ fontSize: '0.85rem' }}>📎 {att.filename}</span>
                  {/* 각 첨부 파일의 상태에 따라 다른 UI를 표시 */}
                  {att.status === 'indexing' && <small className="muted"> (인덱싱 중...)</small>}
                  {att.status === 'failed' && <small style={{ color: '#f87171' }}> (실패)</small>}
                  {att.status === 'temporary' && (
                    // 'temporary' 상태(인덱싱 완료)일 때만 KB 등록 요청 버튼을 표시
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
        {/* 영구 지식베이스(KB) 문서를 필터링하기 위한 드롭다운 */}
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

      {/* 메시지 목록을 렌더링하는 컴포넌트 */}
      <MessageList messages={messages} sendMessage={sendMessage} />

      {/* 메시지 입력 및 파일 첨부를 위한 컴포넌트 */}
      <Composer
        disabled={loading}
        onSend={(text) =>
          sendMessage({
            query: text,
            docFilter: selectedDoc ?? undefined,
          })
        }
        onAttachFile={handleAttachFile}
      />

      {/* KB 등록 요청 모달 (promotingAttachment 상태가 있을 때만 렌더링) */}
      {promotingAttachment && (
        <PromotionModal
          attachment={promotingAttachment}
          onClose={() => setPromotingAttachment(null)}
          onSubmit={(metadata) => {
            handleRequestPromotion(promotingAttachment.attachment_id, metadata);
            setPromotingAttachment(null); // 제출 후 모달 닫기
          }}
        />
      )}
    </section>
  );
}
