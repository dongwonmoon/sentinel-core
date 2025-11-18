/**
 * @file 현재 세션에 컨텍스트를 추가하기 위한 업로드 모달 컴포넌트입니다.
 * @description 이 모달은 사용자에게 여러 방법을 통해 컨텍스트를 추가할 수 있는 UI를 제공합니다.
 * - 로컬 파일(다중) 업로드
 * - 로컬 디렉토리(폴더) 업로드
 * - GitHub 저장소 URL을 통한 코드 임포트
 *
 * 모든 업로드 로직은 `useChatSession` 훅에 위임하여 처리합니다.
 */

import { useState, useRef, useCallback } from "react";
import Modal from "./Modal";
import { useChatSession } from "../hooks/useChatSession"; // ⬅️ 훅 직접 사용
import { useAuth } from "../providers/AuthProvider";

/** SessionUploadModal 컴포넌트가 받는 props의 타입을 정의합니다. */
type Props = {
  /** 모달의 열림/닫힘 상태 */
  isOpen: boolean;
  /** 모달을 닫을 때 호출될 콜백 함수 */
  onClose: () => void;
  /** 파일이 첨부될 현재 채팅 세션의 ID */
  sessionId: string | null; // ⬅️ sessionId를 prop으로 받음
};

/** 모달 내에서 활성화된 탭의 ID를 나타내는 타입입니다. */
type TabId = "files" | "code";

/**
 * 세션별 업로드 모달.
 * 파일/디렉토리/GitHub 세 가지 경로를 모두 `useChatSession` 훅을 통해 백엔드에 위임한다.
 */
export default function SessionUploadModal({ isOpen, onClose, sessionId }: Props) {
  // --- 1. 훅 및 상태 초기화 ---
  const { token } = useAuth();
  // `useChatSession` 훅을 직접 호출하여 업로드 관련 함수들을 가져옵니다.
  const { handleUploadFiles, handleUploadRepo, handleUploadDirectory } = useChatSession(token || '', sessionId);
  
  // 현재 활성화된 탭('files' 또는 'code')을 관리하는 상태
  const [activeTab, setActiveTab] = useState<TabId>("files");
  
  // 숨겨진 파일 입력(input) 엘리먼트에 대한 참조
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // GitHub 저장소 URL 입력 값을 관리하는 상태
  const [repoUrl, setRepoUrl] = useState("");
  
  // 숨겨진 디렉토리 입력 엘리먼트에 대한 참조
  const dirInputRef = useRef<HTMLInputElement>(null);
  // 디렉토리 업로드 시 사용할 그룹 이름을 관리하는 상태
  const [dirName, setDirName] = useState("");

  // GitHub 리포지토리 가져오기 시 로딩 상태를 관리
  const [isLoading, setIsLoading] = useState(false);

  // --- 2. 이벤트 핸들러 ---

  /** 디렉토리 입력(input)이 변경되었을 때(폴더가 선택되었을 때) 호출됩니다. */
  const onDirChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      // 첫 번째 파일의 `webkitRelativePath`에서 디렉토리 이름을 추출하여 기본 그룹 이름으로 사용합니다.
      const firstPath = (e.target.files[0] as any).webkitRelativePath;
      const defaultDirName = firstPath ? firstPath.split('/')[0] : "directory";
      const finalDirName = dirName.trim() || defaultDirName;
      
      handleUploadDirectory(e.target.files, finalDirName);
      onClose(); // 업로드 시작 후 즉시 모달 닫기
      setDirName(""); // 입력 필드 초기화
    }
  };
  
  /** GitHub 저장소 URL 폼이 제출되었을 때 호출됩니다. */
  const onRepoSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.trim()) return;
    setIsLoading(true);
    await handleUploadRepo(repoUrl);
    setIsLoading(false);
    setRepoUrl(""); // 입력 필드 초기화
    onClose(); // 업로드 시작 후 즉시 모달 닫기
  };

  /** 모달이 닫힐 때 모든 내부 상태를 초기화하는 핸들러입니다. */
  const handleClose = () => {
    setActiveTab("files");
    setRepoUrl("");
    setDirName("");
    onClose();
  };

  // 모달이 닫혀 있으면 아무것도 렌더링하지 않습니다.
  if (!isOpen) return null;

  // --- 3. UI 렌더링 ---
  return (
    <Modal onClose={handleClose} width="min(500px, 90vw)">

      <div className="panel-form" style={{ marginTop: '1.5rem', background: 'var(--color-app-bg)', padding: '1rem', borderRadius: '12px' }}>
        <h4 style={{ marginTop: 0 }}>코드 가져오기</h4>
        
        {/* GitHub URL 입력 폼 */}
        <form onSubmit={onRepoSubmit} style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            type="url"
            placeholder="GitHub 저장소 또는 브랜치 URL"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            required
            style={{ flex: 1, margin: 0 }}
          />
          <button type="submit" className="primary" disabled={isLoading} style={{ padding: '0 1.2rem' }}>
            {isLoading ? "..." : "가져오기"}
          </button>
        </form>

        <hr style={{ border: 'none', borderTop: '1px solid var(--color-panel-border)', margin: '1rem 0' }} />

        {/* 로컬 디렉토리 업로드 폼 */}
        <input
          ref={dirInputRef}
          type="file"
          //@ts-ignore
          webkitdirectory="true"
          directory="true"
          multiple
          onChange={onDirChange}
          style={{ display: 'none' }}
        />
        <label style={{ fontSize: '0.9rem' }}>또는 로컬 폴더 업로드:</label>
        <input
          type="text"
          placeholder="그룹 이름 (선택, 기본값: 폴더명)"
          value={dirName}
          onChange={(e) => setDirName(e.target.value)}
          style={{ margin: 0 }}
        />
        <button 
          type="button" 
          className="ghost" 
          onClick={() => dirInputRef.current?.click()}
          style={{ width: '100%', background: 'white' }}
        >
          폴더 업로드
        </button>
      </div>
    </Modal>
  );
}