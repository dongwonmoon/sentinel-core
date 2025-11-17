import { useState, useRef, useMemo } from "react";
import { useAuth } from "../providers/AuthProvider";
import { apiRequest } from "../lib/apiClient";
import { notify } from "./NotificationHost";
import Modal from "./Modal";
import PanelTabs from "./PanelTabs";

type AddKnowledgeModalProps = {
  onClose: () => void;
  onTasksSubmitted: (taskIds: string[]) => void; // ⬅️ 여러 task ID를 전달
};

type TabId = "files" | "code";

export default function AddKnowledgeModal({ onClose, onTasksSubmitted }: AddKnowledgeModalProps) {
  const { token } = useAuth();
  const [activeTab, setActiveTab] = useState<TabId>("files");

  // --- 폼 상태 ---
  // 탭 1: 파일
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [filePermissionGroups, setFilePermissionGroups] = useState("all_users");
  
  // 탭 2: 코드 (폴더)
  const [selectedDirectory, setSelectedDirectory] = useState<FileList | null>(null);
  const dirInputRef = useRef<HTMLInputElement>(null);
  const [dirGroupName, setDirGroupName] = useState("");
  const [dirPermissionGroups, setDirPermissionGroups] = useState("all_users");

  // 탭 2: 코드 (GitHub)
  const [repoUrl, setRepoUrl] = useState("");

  const [isLoading, setIsLoading] = useState(false);

  // --- 제출 핸들러 ---

  // 1. (신규) '파일 업로드' 탭 핸들러 (개별 API 호출)
  const handleUploadFiles = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selectedFiles || selectedFiles.length === 0) {
      notify("업로드할 파일을 선택하세요.");
      return;
    }
    if (!token) {
      notify("인증 정보가 없습니다.");
      return;
    }

    setIsLoading(true);
    const taskIds: string[] = [];
    const failedFiles: string[] = [];
    const permissions = JSON.stringify(filePermissionGroups.split(",").map(g => g.trim()));

    for (let i = 0; i < selectedFiles.length; i++) {
      const file = selectedFiles[i];
      const formData = new FormData();
      formData.append("file", file);
      formData.append("permission_groups_json", permissions);

      try {
        const result = await apiRequest<{ task_id: string }>(
          "/documents/upload-single-file", // ⬅️ (중요) 새 API 호출
          {
            method: "POST",
            token,
            body: formData,
            errorMessage: `${file.name} 업로드 실패`,
          }
        );
        taskIds.push(result.task_id);
      } catch (err) {
        failedFiles.push(file.name);
        notify(err instanceof Error ? err.message : `${file.name} 업로드 오류`);
      }
    }

    setIsLoading(false);
    if (taskIds.length > 0) {
      notify(`${taskIds.length}개 파일의 인덱싱 작업을 시작합니다.`);
      onTasksSubmitted(taskIds); // ⬅️ 성공한 작업 ID 목록 전달
    }
    if (failedFiles.length > 0) {
      notify(`실패: ${failedFiles.join(", ")}`);
    }
  };

  // 2. (기존) '디렉토리 업로드' 탭 핸들러 (그룹 API 호출)
  const handleUploadDirectory = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selectedDirectory || selectedDirectory.length === 0) {
      notify("업로드할 디렉토리를 선택하세요.");
      return;
    }
    if (!dirGroupName.trim()) {
      notify("디렉토리 그룹 이름을 입력하세요.");
      return;
    }
    if (!token) return;

    const formData = new FormData();
    for (let i = 0; i < selectedDirectory.length; i++) {
      const file = selectedDirectory[i];
      const path = (file as any).webkitRelativePath || file.name;
      formData.append("files", file, path);
    }
    
    formData.append("display_name", dirGroupName.trim());
    formData.append("permission_groups_json", JSON.stringify(
      dirPermissionGroups.split(",").map(g => g.trim())
    ));

    setIsLoading(true);
    try {
      const result = await apiRequest<{ task_id: string }>(
        "/documents/upload-and-index", // ⬅️ (중요) 기존 그룹 API 호출
        { method: "POST", token, body: formData, errorMessage: "디렉토리 업로드 실패" }
      );
      notify(`'${dirGroupName}' 그룹 인덱싱을 시작합니다.`);
      onTasksSubmitted([result.task_id]);
    } catch (err) {
      notify(err instanceof Error ? err.message : "업로드 오류");
    } finally {
      setIsLoading(false);
    }
  };

  // 3. (기존) 'GitHub' 핸들러
  const handleRepoSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!repoUrl.trim() || !token) return;

    setIsLoading(true);
    try {
      const result = await apiRequest<{ task_id: string }>(
        "/documents/index-github-repo",
        { method: "POST", token, json: { repo_url: repoUrl }, errorMessage: "레포 인덱싱 실패" }
      );
      notify("GitHub 인덱싱을 시작했습니다.");
      onTasksSubmitted([result.task_id]);
    } catch (err) {
      notify(err instanceof Error ? err.message : "인덱싱 오류");
    } finally {
      setIsLoading(false);
    }
  };

  const fileLabel = useMemo(() => {
    if (!selectedFiles) return "파일을 선택하세요 (다중 선택 가능)";
    if (selectedFiles.length === 1) return selectedFiles[0].name;
    return `${selectedFiles.length}개의 파일이 선택됨`;
  }, [selectedFiles]);

  const dirLabel = useMemo(() => {
    if (!selectedDirectory) return "디렉토리를 선택하세요";
    // webkitRelativePath에서 첫 번째 폴더 이름을 그룹 이름으로 제안
    const firstPath = (selectedDirectory[0] as any).webkitRelativePath;
    const dirName = firstPath ? firstPath.split('/')[0] : "디렉토리";
    if (dirName !== dirGroupName) setDirGroupName(dirName); // ⬅️ 그룹 이름 자동 추천
    return `${dirName} (${selectedDirectory.length}개 파일)`;
  }, [selectedDirectory]);

  return (
    <Modal onClose={onClose} width="min(600px, 90vw)">
      <h2 style={{ marginTop: 0 }}>새 지식 소스 추가</h2>
      <PanelTabs
        activeId={activeTab}
        onChange={(id) => setActiveTab(id as TabId)}
        tabs={[
          { id: "files", label: "파일 업로드" },
          { id: "code", label: "코드 가져오기" },
        ]}
      />

      <div style={{ paddingTop: "1.5rem" }}>
        {/* === 탭 1: 파일 업로드 (개별) === */}
        <div className={`fade-in-out ${activeTab === "files" ? "active" : ""}`}>
          {activeTab === "files" && (
            <form onSubmit={handleUploadFiles} className="panel-form">
              <p className="muted">
                개별 파일(PDF, TXT, MD...) 또는 ZIP 파일을 업로드합니다.<br/>
                각 파일은 목록에 개별 항목으로 등록됩니다.
              </p>
              <label>
                1. 파일 선택 (다중 선택 가능)
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".zip,.txt,.md,.pdf,.py,.js,.ts,.java,.c,.h,.cpp,.go"
                  onChange={(e) => setSelectedFiles(e.target.files)}
                  required
                  style={{display: 'none'}}
                />
                <button type="button" className="ghost" onClick={() => fileInputRef.current?.click()}>
                  {fileLabel}
                </button>
              </label>
              <label>
                2. 권한 그룹 (쉼표로 구분)
                <input
                  type="text"
                  value={filePermissionGroups}
                  onChange={(e) => setFilePermissionGroups(e.target.value)}
                  required
                />
              </label>
              <button type="submit" className="primary" disabled={isLoading || !selectedFiles}>
                {isLoading ? "업로드 중..." : `파일 ${selectedFiles?.length || 0}개 업로드`}
              </button>
            </form>
          )}
        </div>

        {/* === 탭 2: 코드 가져오기 (그룹) === */}
        <div className={`fade-in-out ${activeTab === "code" ? "active" : ""}`}>
          {activeTab === "code" && (
            <div className="panel-form" style={{gap: '2rem'}}>
              {/* 2-A: 로컬 디렉토리 */}
              <form onSubmit={handleUploadDirectory}>
                <h4>로컬 디렉토리</h4>
                <p className="muted">로컬 코드베이스 폴더를 선택합니다. 폴더 전체가 하나의 '그룹'으로 등록됩니다.</p>
                <label>
                  1. 디렉토리 그룹 이름 (필수)
                  <input
                    type="text"
                    placeholder="예: my-project-v1"
                    value={dirGroupName}
                    onChange={(e) => setDirGroupName(e.target.value)}
                    required
                  />
                </label>
                <label>
                  2. 디렉토리 선택
                  <input
                    ref={dirInputRef}
                    type="file"
                    //@ts-ignore
                    webkitdirectory="true"
                    directory="true"
                    multiple
                    onChange={(e) => setSelectedDirectory(e.target.files)}
                    required
                    style={{display: 'none'}}
                  />
                  <button type="button" className="ghost" onClick={() => dirInputRef.current?.click()}>
                    {dirLabel}
                  </button>
                </label>
                <label>
                  3. 권한 그룹
                  <input
                    type="text"
                    value={dirPermissionGroups}
                    onChange={(e) => setDirPermissionGroups(e.target.value)}
                    required
                  />
                </label>
                <button type="submit" className="primary" disabled={isLoading || !selectedDirectory}>
                  {isLoading ? "업로드 중..." : "디렉토리 업로드"}
                </button>
              </form>
              
              <hr style={{border: 'none', borderTop: '1px solid var(--color-panel-border)'}} />

              {/* 2-B: GitHub */}
              <form onSubmit={handleRepoSubmit}>
                <h4>GitHub 리포지토리</h4>
                <p className="muted">Public 리포지토리를 통째로 하나의 '그룹'으로 등록합니다.</p>
                <label>
                  GitHub 리포지토리 URL
                  <input
                    type="url"
                    placeholder="https://github.com/user/repo"
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    required
                  />
                </label>
                <button type="submit" className="primary" disabled={isLoading || !repoUrl}>
                  {isLoading ? "인덱싱 중..." : "GitHub에서 가져오기"}
                </button>
              </form>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}