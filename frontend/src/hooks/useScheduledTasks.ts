import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../lib/apiClient";
import { notify } from "../components/NotificationHost";

// 백엔드 scheduler.py의 TaskResponse 스키마와 일치
export type ScheduledTask = {
  task_id: number;
  task_name: string;
  schedule: string;
  task_kwargs: {
    repo_url?: string;
  };
  is_active: boolean;
};

// 백엔드 scheduler.py의 TaskCreate 스키마와 일치
export type TaskCreate = {
  task_name: string;
  schedule: string;
  task_kwargs: Record<string, string>;
};

export function useScheduledTasks(token: string) {
  const queryClient = useQueryClient();

  // 1. GET /scheduler/tasks (조회)
  const { data: tasks, isLoading } = useQuery({
    queryKey: ["scheduledTasks"],
    queryFn: () =>
      apiRequest<ScheduledTask[]>("/scheduler/tasks", {
        token,
        errorMessage: "반복 작업을 불러오지 못했습니다.",
      }),
    enabled: !!token,
  });

  // 2. POST /scheduler/tasks (생성)
  const { mutate: createTask, isPending: isCreating } = useMutation({
    mutationFn: (newTask: TaskCreate) =>
      apiRequest<ScheduledTask>("/scheduler/tasks", {
        method: "POST",
        token,
        json: newTask,
        errorMessage: "작업 등록에 실패했습니다.",
      }),
    onSuccess: () => {
      notify("반복 작업이 등록되었습니다.");
      queryClient.invalidateQueries({ queryKey: ["scheduledTasks"] });
    },
    onError: (err) => {
      notify(err.message);
    },
  });

  // 3. DELETE /scheduler/tasks/{task_id} (삭제)
  const { mutate: deleteTask, isPending: isDeleting } = useMutation({
    mutationFn: (taskId: number) =>
      apiRequest(`/scheduler/tasks/${taskId}`, {
        method: "DELETE",
        token,
        errorMessage: "작업 삭제에 실패했습니다.",
      }),
    onSuccess: () => {
      notify("작업이 삭제되었습니다.");
      queryClient.invalidateQueries({ queryKey: ["scheduledTasks"] });
    },
    onError: (err) => {
      notify(err.message);
    },
  });

  return {
    tasks: tasks || [],
    isLoading,
    createTask,
    deleteTask,
    isPending: isCreating || isDeleting,
  };
}