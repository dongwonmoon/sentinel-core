import { useState, useRef } from "react";
import { AuthResult } from "./AuthView";
import { notify } from "./NotificationHost";
import { apiRequest } from "../lib/apiClient";
import { useTaskPolling, TaskStatusResponse } from "../hooks/useTaskPolling";

type Props = {
  auth: AuthResult;
  documents: { id: string; name: string }[];
  onRefresh: () => void;
  onSelectDoc: (id: string | null) => void;
};

export default function ContextPanel({ auth, documents, onRefresh, onSelectDoc }: Props) {
  const [uploadLoading, setUploadLoading] = useState(false);
  const [repoUrl, setRepoUrl] = useState("");
  const [repoLoading, setRepoLoading] = useState(false);
  const [knowledgeName, setKnowledgeName] = useState("");
  const [uploadGroups, setUploadGroups] = useState<string[]>(["all_users"]);
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dirInputRef = useRef<HTMLInputElement>(null);

  const { startPolling } = useTaskPolling({
    token: auth.token,
    onSuccess: (response) => {
      notify(extractResultMessage(response, "인덱싱 완료!"));
      onRefresh();
    },
    onFailure: (response) =>
      notify(extractResultMessage(response, "인덱싱 실패")),
    onError: (err) => notify(err.message),
    onTimeout: () => notify("인덱싱 시간이 초과되었습니다."),
  });

  async function handleUpload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selectedFiles || selectedFiles.length === 0) {
      notify("업로드할 파일 또는 디렉토리를 선택해야 합니다.");
      return;
    }
    if (!knowledgeName.trim()) {
      notify("지식 소스 이름을 입력해야 합니다.");
      return;
    }

    const formData = new FormData();

    for (let i = 0; i < selectedFiles.length; i++) {
      const file = selectedFiles[i];
      // 디렉토리 선택 시 webkitRelativePath에 'MyProject/src/main.py'가 들어옴
      // 파일 선택 시 file.name에 'main.py'가 들어옴
      const path = (file as any).webkitRelativePath || file.name;
      formData.append("files", file, path);
    }

    // 2. [수정] 👈 지식 소스 이름과 권한 그룹을 FormData에 추가
    const displayName = knowledgeName.trim();
    formData.append("display_name", displayName); // 👈 사용자가 입력한 이름
    formData.append("permission_groups_json", JSON.stringify(uploadGroups));

    setUploadLoading(true);
    try {
      const result = await apiRequest<{ task_id: string }>(
        "/documents/upload-and-index",
        {
          method: "POST",
          token: auth.token,
          body: formData,
          errorMessage: "업로드 실패",
        },
      );
      notify(`'${displayName}' 인덱싱을 시작했습니다.`);
      
      // 상태 초기화
      setKnowledgeName("");
      setSelectedFiles(null);
      e.currentTarget.reset();
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (dirInputRef.current) dirInputRef.current.value = "";
      
      startPolling(result.task_id);
      
    } catch (err) {
      notify(err instanceof Error ? err.message : "업로드 중 오류");
    } finally {
      setUploadLoading(false);
    }
  }

  async function handleRepo(e: React.FormEvent) {
    e.preventDefault();
    if (!repoUrl) return;
    setRepoLoading(true);
    try {
      const result = await apiRequest<{ task_id: string }>(
        "/documents/index-github-repo",
        {
          method: "POST",
          token: auth.token,
          json: { repo_url: repoUrl },
          errorMessage: "레포 인덱싱 실패",
        },
      );
      notify("GitHub 인덱싱을 시작했습니다.");
      setRepoUrl("");
      startPolling(result.task_id);
    } catch (err) {
      notify(err instanceof Error ? err.message : "인덱싱 오류");
    } finally {
      setRepoLoading(false);
    }
  }

  async function handleDelete(docId: string) {
    if (!confirm("정말 삭제하시겠습니까?")) return;
    try {
      await apiRequest("/documents", {
        method: "DELETE",
        token: auth.token,
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

  return (
    <aside className="context-panel">
      <section>
        <h3>지식 소스</h3>
        <div className="doc-list">
          {documents.length === 0 && <p className="muted">인덱싱된 문서가 없습니다.</p>}
          {documents.map((doc) => (
            <div key={doc.id} className="doc-item">
              <button onClick={() => onSelectDoc(doc.id)}>{doc.name}</button>
              <button className="ghost" onClick={() => handleDelete(doc.id)}>
                삭제
              </button>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h4>파일/디렉토리 업로드</h4>
        <form className="panel-form" onSubmit={handleUpload}>
          <label>
            1. 지식 소스 이름 (필수)
            <input
              type="text"
              value={knowledgeName}
              onChange={(e) => setKnowledgeName(e.target.value)}
              placeholder="e.g., 나의 파이썬 프로젝트"
              required
            />
          </label>
          <label>
            2. 적용할 권한 그룹
            <input
              value={uploadGroups.join(",")}
              onChange={(e) =>
                setUploadGroups(e.target.value.split(",").map((g) => g.trim()))
              }
              placeholder="all_users, it"
            />
          </label>
          <label>
            3. 파일 또는 디렉토리 선택
          </label>
          <input
            type="file"
            ref={fileInputRef}
            onChange={(e) => setSelectedFiles(e.target.files)}
            multiple
            style={{ display: "none" }}
            accept=".txt,.md,.pdf,.py,.js,.ts,.java,.go,.c,.cpp,.h" // 👈 파일 제한
          />
          <input
            type="file"
            ref={dirInputRef}
            onChange={(e) => setSelectedFiles(e.target.files)}
            // @ts-ignore
            webkitdirectory="true"
            style={{ display: "none" }}
          />
          <div style={{ display: "flex", gap: "0.5rem", width: "100%" }}>
            <button
              type="button"
              className="ghost" //
              onClick={() => fileInputRef.current?.click()}
              style={{ flex: 1 }}
            >
              파일 선택
            </button>
            <button
              type="button"
              className="ghost" //
              onClick={() => dirInputRef.current?.click()}
              style={{ flex: 1 }}
            >
              디렉토리 선택
            </button>
          </div>
          {/* 선택된 파일 정보 표시 */}
          {selectedFiles && selectedFiles.length > 0 && (
            <p className="muted" style={{ fontSize: '0.8rem', margin: '0.5rem 0 0 0' }}>
              {selectedFiles.length}개 파일/디렉토리 선택됨
            </p>
          )}

          {/* 최종 제출 버튼 */}
          <button
            type="submit"
            disabled={uploadLoading || !selectedFiles?.length || !knowledgeName.trim()}
          >
            {uploadLoading ? "업로드 중..." : "업로드 시작"}
          </button>
        </form>
      </section>

      <section>
        <h4>GitHub 인덱싱</h4>
        <form className="panel-form" onSubmit={handleRepo}>
          <input
            type="url"
            placeholder="https://github.com/org/repo"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            required
          />
          <button type="submit" disabled={repoLoading}>
            {repoLoading ? "요청 중..." : "시작"}
          </button>
        </form>
      </section>
    </aside>
  );
}

function extractResultMessage(
  response: TaskStatusResponse,
  fallback: string,
) {
  if (!response.result) return fallback;
  if (typeof response.result === "string") return response.result;
  return response.result.message ?? fallback;
}
