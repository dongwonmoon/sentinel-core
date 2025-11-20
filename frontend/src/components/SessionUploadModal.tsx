/**
 * @file 현재 세션에 컨텍스트를 추가하기 위한 업로드 모달 컴포넌트입니다.
 * @description Gemini 스타일의 UI를 적용하여 중앙 모달 형태로 GitHub URL 입력 및 폴더 업로드를 제공합니다.
 */

import { useState, useRef } from "react";
import Modal from "./Modal";
import { useChatSession } from "../hooks/useChatSession";
import { useAuth } from "../providers/AuthProvider";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string | null;
};

export default function SessionUploadModal({ isOpen, onClose, sessionId }: Props) {
  const { token } = useAuth();
  const { handleUploadRepo, handleUploadDirectory } = useChatSession(token || '', sessionId);
  
  const [repoUrl, setRepoUrl] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  
  // 숨겨진 파일 입력 참조
  const dirInputRef = useRef<HTMLInputElement>(null);

  // --- 핸들러 ---

  // GitHub URL 제출
  const onRepoSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.trim()) return;
    setIsLoading(true);
    await handleUploadRepo(repoUrl);
    setIsLoading(false);
    setRepoUrl("");
    onClose();
  };

  // 폴더 업로드 처리
  const onDirChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const firstPath = (e.target.files[0] as any).webkitRelativePath;
      const defaultDirName = firstPath ? firstPath.split('/')[0] : "directory";
      
      // 폴더명은 별도 입력 없이 폴더 이름 그대로 사용 (Gemini UX 단순화)
      handleUploadDirectory(e.target.files, defaultDirName);
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    // Modal의 기본 width를 override하여 조금 더 넓게 설정할 수 있습니다.
    <Modal onClose={onClose} width="600px">
      <div className="gemini-modal-container">
        
        {/* 헤더 영역: 제목과 닫기 버튼 */}
        <div className="gemini-modal-header">
          <h2>코드 가져오기</h2>
          <button onClick={onClose} className="close-btn">×</button>
        </div>

        {/* GitHub 입력 폼 */}
        <form onSubmit={onRepoSubmit} className="gemini-input-group">
          <input
            type="url"
            placeholder="GitHub 저장소 또는 브랜치 URL"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            required
            className="gemini-input"
            disabled={isLoading}
          />
          <button type="submit" className="gemini-primary-btn" disabled={isLoading}>
            {isLoading ? "..." : "가져오기"}
          </button>
        </form>

        {/* 하단 폴더 업로드 링크 */}
        <div className="gemini-footer-actions">
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
          <button 
            type="button" 
            className="gemini-link-btn"
            onClick={() => dirInputRef.current?.click()}
          >
            폴더 업로드
          </button>
        </div>

      </div>
    </Modal>
  );
}