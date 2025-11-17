import { useState, useRef, useCallback } from "react";
import Modal from "./Modal";
import { useChatSession } from "../hooks/useChatSession"; // ⬅️ 훅 직접 사용
import { useAuth } from "../providers/AuthProvider";
import { notify } from "./NotificationHost";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string | null; // ⬅️ sessionId를 prop으로 받음
};

type TabId = "files" | "code";

export default function SessionUploadModal({ isOpen, onClose, sessionId }: Props) {
  const { token } = useAuth();
  // ⬅️ 모달이 `useChatSession` 훅을 직접 호출하여 함수 사용
  const { handleUploadFiles, handleUploadRepo, handleUploadDirectory } = useChatSession(token || '', sessionId);
  
  const [activeTab, setActiveTab] = useState<TabId>("files");
  
  // 파일 업로드 (Tab 1)
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // 코드 가져오기 - GitHub (Tab 2)
  const [repoUrl, setRepoUrl] = useState("");
  
  // 코드 가져오기 - 디렉토리 (Tab 2)
  const dirInputRef = useRef<HTMLInputElement>(null);
  const [dirName, setDirName] = useState("");

  const [isLoading, setIsLoading] = useState(false);

  // --- 핸들러 ---

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleUploadFiles(e.target.files);
      onClose(); // 업로드 후 모달 닫기
    }
  };

  const onDirChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      // 첫 파일의 webkitRelativePath에서 디렉토리 이름 추출
      const firstPath = (e.target.files[0] as any).webkitRelativePath;
      const defaultDirName = firstPath ? firstPath.split('/')[0] : "directory";
      const finalDirName = dirName.trim() || defaultDirName;
      
      // 브라우저에서 폴더 전체를 고르면 FileList가 경로 정보를 포함하므로 그대로 훅에 넘긴다.
      handleUploadDirectory(e.target.files, finalDirName);
      onClose(); // 업로드 후 모달 닫기
      setDirName(""); // 상태 초기화
    }
  };
  
  const onRepoSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.trim()) return;
    setIsLoading(true);
    await handleUploadRepo(repoUrl);
    setIsLoading(false);
    setRepoUrl(""); // 상태 초기화
    onClose(); // 업로드 후 모달 닫기
  };

  // 모달이 닫힐 때 state 초기화
  const handleClose = () => {
    setActiveTab("files");
    setRepoUrl("");
    setDirName("");
    onClose();
  };

  if (!isOpen) return null;

  return (
    <Modal onClose={handleClose} width="min(500px, 90vw)">
      {/* 이 부분은 image_294368.png 처럼 탭이 아닌
        단순 버튼 목록으로 구현하는 것이 더 간결합니다.
      */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        
        {/* 1. 파일 업로드 */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".zip,.txt,.md,.pdf,.py,.js,.ts,.java,.c,.h,.cpp,.go, .png, .jpg, .jpeg"
          onChange={onFileChange}
          style={{ display: "none" }}
        />
        <button 
          className="list-item" 
          onClick={() => fileInputRef.current?.click()}
          style={{ textAlign: 'left', background: 'var(--color-hover-bg)' }}
        >
          <span style={{ fontSize: '1.2rem', marginRight: '1rem' }}>📎</span>
          파일 업로드 (다중 선택 가능)
        </button>
        
        {/* 2. 코드 가져오기 (탭으로 변경) */}
        <button 
          className="list-item" 
          onClick={() => setActiveTab("code")}
          style={{ textAlign: 'left', background: 'var(--color-hover-bg)' }}
        >
          <span style={{ fontSize: '1.2rem', marginRight: '1rem' }}>&lt;/&gt;</span>
          코드 가져오기
        </button>
      </div>

      {/* "코드 가져오기" 선택 시 하단에 폼 표시 (image_2943fc.png) */}
      {activeTab === "code" && (
        <div className="panel-form" style={{ marginTop: '1.5rem', background: 'var(--color-app-bg)', padding: '1rem', borderRadius: '12px' }}>
          <h4 style={{ marginTop: 0 }}>코드 가져오기</h4>
          
          {/* GitHub 폼 */}
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

          {/* 디렉토리 업로드 폼 */}
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
      )}
    </Modal>
  );
}
