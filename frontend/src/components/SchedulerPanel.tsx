import { useMemo, useState } from "react";
import { useScheduledTasks, TaskCreate } from "../hooks/useScheduledTasks";
import { useAuth } from "../providers/AuthProvider";

const CRON_PRESETS = [
  { label: "매일 오전 9시", value: "0 9 * * *" },
  { label: "매일 오후 6시", value: "0 18 * * *" },
  { label: "매시간 0분", value: "0 * * * *" },
  { label: "매주 월요일 10시", value: "0 10 * * 1" },
];

export default function SchedulerPanel() {
  const { user } = useAuth();
  if (!user) return null;

  const { tasks, isLoading, createTask, deleteTask, isPending } =
    useScheduledTasks(user.token);
  
  // 새 작업 등록을 위한 폼 상태
  const [repoUrl, setRepoUrl] = useState("");
  const [schedule, setSchedule] = useState("0 9 * * *");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.trim() || !schedule.trim()) {
      alert("레포지토리 URL과 스케줄(Crontab)을 입력해야 합니다.");
      return;
    }

    if (!isValidCron(schedule.trim())) {
      setError("유효한 Crontab 형식(5 필드)을 입력하세요.");
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
        setError(null);
      }
    });
  };

  const taskCountLabel = useMemo(() => {
    if (isLoading) return "로딩 중";
    if (tasks.length === 0) return "등록된 작업 없음";
    return `${tasks.length}건 등록됨`;
  }, [isLoading, tasks.length]);

  return (
    // context-panel 스타일 재사용
    <aside className="context-panel">
      <section>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3>반복 작업 목록</h3>
          <small className="muted">{taskCountLabel}</small>
        </div>
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
        <p className="muted" style={{ fontSize: "0.8rem" }}>
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
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {CRON_PRESETS.map((preset) => (
              <button
                key={preset.value}
                type="button"
                className="ghost"
                onClick={() => setSchedule(preset.value)}
              >
                {preset.label}
              </button>
            ))}
          </div>
          {error && (
            <p className="auth-error" style={{ margin: 0 }}>{error}</p>
          )}
          <button type="submit" disabled={isPending}>
            {isPending ? "등록 중..." : "반복 작업 등록"}
          </button>
        </form>
      </section>
    </aside>
  );
}

function isValidCron(value: string) {
  const parts = value.trim().split(/\s+/);
  return parts.length === 5;
}
