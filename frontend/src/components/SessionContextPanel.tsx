/**
 * @file 현재 채팅 세션의 컨텍스트(첨부 파일 등)를 표시하는 우측 패널 UI 컴포넌트입니다.
 * @description 이 패널은 사용자가 현재 대화에서 참고하고 있는 파일들의 목록을 보여주고,
 * 각 파일의 상태(인덱싱 중, 준비 완료 등)를 시각적으로 나타냅니다.
 * 또한, 사용자가 더 이상 필요 없는 파일을 세션에서 제거할 수 있는 기능을 제공합니다.
 */

import { SessionAttachment } from "../hooks/useChatSession";

/** SessionContextPanel 컴포넌트가 받는 props의 타입을 정의합니다. */
type Props = {
  /**
   * 현재 세션에 첨부된 파일의 목록.
   * `useChatSession` 훅으로부터 전달받습니다.
   */
  attachments: SessionAttachment[];
  /**
   * 특정 첨부 파일을 세션에서 삭제할 때 호출될 콜백 함수입니다.
   * @param attachmentId 삭제할 첨부 파일의 고유 ID
   */
  onDeleteAttachment: (attachmentId: number) => void;
};

export default function SessionContextPanel({ attachments, onDeleteAttachment }: Props) {
  // 첨부 파일 목록이 비어있는지 여부를 나타내는 변수
  const isEmpty = attachments.length === 0;

  return (
    // context-panel 스타일 재사용
    <aside className="context-panel" style={{ background: 'var(--color-panel-bg)'}}>
      <section style={{ background: 'transparent', border: 'none', padding: 0 }}>
        {/* 패널 헤더 */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: '1rem' }}>
          <h3>세션 컨텍스트</h3>
          <small className="muted">{attachments.length}개 항목</small>
        </div>
        <p className="muted" style={{ padding: '0 1rem', marginTop: '-0.5rem', fontSize: '0.9rem' }}>
          이 대화에서만 참고하는 파일 목록입니다.
        </p>
        {/* 첨부파일은 세션 내 RAG 전용이므로 상태만 간단히 보여준다. */}
        <div className="doc-list" style={{ maxHeight: 'calc(100vh - 100px)', padding: '0 1rem' }}>
          {/* 목록이 비어있을 경우 안내 메시지를 표시합니다. */}
          {isEmpty && <p className="muted" style={{textAlign: 'center', paddingTop: '1rem'}}>+ 버튼으로 파일을 추가하세요.</p>}
          
          {/* `attachments` 배열을 순회하며 각 첨부 파일을 UI 요소로 렌더링합니다. */}
          {attachments.map((att) => (
            <div key={att.attachment_id || att.task_id} className="doc-item">
              <div style={{ flex: 1, overflow: 'hidden' }}>
                {/* 파일명과 상태 아이콘 */}
                <p style={{ margin: 0, fontWeight: 600, fontSize: '0.9rem', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }} title={att.filename}>
                  {att.status === 'indexing' ? '🔄' : '📎'} {att.filename}
                </p>
                {/* 파일 상태 텍스트 */}
                <small className="muted">
                  {att.status === 'indexing' && '인덱싱 중...'}
                  {att.status === 'temporary' && 'RAG 준비 완료'}
                  {att.status === 'failed' && '인덱싱 실패'}
                </small>
              </div>
              {/* 파일 삭제 버튼 */}
              <button
                className="ghost"
                style={{ padding: '0.2rem', width: '30px', height: '30px' }}
                onClick={() => onDeleteAttachment(att.attachment_id)}
                title="세션에서 제거"
              >
                X
              </button>
            </div>
          ))}
        </div>
      </section>
    </aside>
  );
}
