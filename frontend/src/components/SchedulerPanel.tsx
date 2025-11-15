import { useState } from "react";
import { AuthResult } from "./AuthView";
import { useScheduledTasks, TaskCreate } from "../hooks/useScheduledTasks";

type Props = {
  auth: AuthResult;
};

export default function SchedulerPanel({ auth }: Props) {
  const { tasks, isLoading, createTask, deleteTask, isPending } =
    useScheduledTasks(auth.token);
  
  // 새 작업 등록을 위한 폼 상태
  const [repoUrl, setRepoUrl] = useState("");
  const [schedule, setSchedule] = useState("0 9 * * *"); // 기본값: 매일 오전 9시

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.trim() || !schedule.trim()) {
      alert("레포지토리 URL과 스케줄(Crontab)을 입력해야 합니다.");
      return;
    }

    const newTask: TaskCreate = {
      task_name: "run_scheduled_github_summary", // 👈 tasks.py에 하드코딩된 이름
      schedule: schedule.trim(),
      task_kwargs: {
        repo_url: repoUrl.trim(),
      },
    };
    createTask(newTask, {
      onSuccess: () => {
        setRepoUrl(""); // 폼 초기화
      }
    });
  };

  return (
    // context-panel 스타일 재사용
    <aside className="context-panel">
      <section>
        <h3>반복 작업 목록</h3>
        <div className="doc-list">
          {isLoading && <p className="muted">로딩 중...</p>}
          {!isLoading && tasks.length === 0 && (
            <p className="muted">등록된 반복 작업이 없습니다.</p>
          )}
          {tasks.map((task) => (
            <div key={task.task_id} className="doc-item">
              <div style={{ flex: 1 }}>
                <p style={{ margin: 0, fontWeight: 600, fontSize: '0.9rem' }}>
                  {task.task_kwargs.repo_url?.split("/").slice(-1)[0]} 요약
                </p>
                <small className="muted">{task.schedule}</small>
              </div>
              <button
                className="ghost"
                onClick={() => deleteTask(task.task_id)}
                disabled={isPending}
              >
                삭제
              </button>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h4>신규 GitHub 요약 등록</h4>
        <p className="muted" style={{ fontSize: '0.8rem' }}>
          지정한 스케줄(Crontab)에 따라 24시간 내 커밋을 요약하여 알림을 보냅니다.
        </p>
        <form className="panel-form" onSubmit={handleSubmit}>
          <label>
            1. GitHub 레포지토리 URL
            <input
              type="url"
              placeholder="https://github.com/org/repo"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              required
            />
          </label>
          <label>
            2. Crontab 스케줄
            <input
              type="text"
              value={schedule}
              onChange={(e) => setSchedule(e.target.value)}
              required
            />
          </label>
          <button type="submit" disabled={isPending}>
            {isPending ? "등록 중..." : "반복 작업 등록"}
          </button>
        </form>
      </section>
    </aside>
  );
}