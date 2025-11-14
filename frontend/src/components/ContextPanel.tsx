import { useState } from "react";
import { AuthResult } from "./AuthView";
import { notify } from "./NotificationHost";
import { getApiBaseUrl } from "../hooks/useEnvironment";
const API_BASE = getApiBaseUrl();

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

  async function handleUpload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fileInput = e.currentTarget.elements.namedItem("file") as HTMLInputElement;
    if (!fileInput.files?.length) return;
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    setUploadLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/documents/upload-and-index`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${auth.token}`,
          },
          body: formData,
        },
      );
      if (!res.ok) throw new Error("업로드 실패");
      notify("업로드 및 인덱싱을 시작했습니다.");
      fileInput.value = "";
      onRefresh();
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
      const res = await fetch(
        `${API_BASE}/documents/index-github-repo`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${auth.token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ repo_url: repoUrl }),
        },
      );
      if (!res.ok) throw new Error("레포 인덱싱 실패");
      notify("GitHub 인덱싱을 시작했습니다.");
      setRepoUrl("");
    } catch (err) {
      notify(err instanceof Error ? err.message : "인덱싱 오류");
    } finally {
      setRepoLoading(false);
    }
  }

  async function handleDelete(docId: string) {
    if (!confirm("정말 삭제하시겠습니까?")) return;
    try {
      const res = await fetch(
        `${API_BASE}/documents`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${auth.token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ doc_id_or_prefix: docId }),
        },
      );
      if (!res.ok) throw new Error("삭제 실패");
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
        <h4>파일 업로드</h4>
        <form className="panel-form" onSubmit={handleUpload}>
          <input type="file" name="file" accept=".txt,.md,.pdf,.zip" required />
          <button type="submit" disabled={uploadLoading}>
            {uploadLoading ? "업로드 중..." : "업로드"}
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
