import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../lib/apiClient";

export type TaskStatusResponse = {
  status: "PENDING" | "SUCCESS" | "FAILURE";
  result?: { message?: string } | string | null;
};

type UseTaskPollingOptions = {
  token: string;
  buildStatusPath?: (taskId: string) => string;
  intervalMs?: number;
  timeoutMs?: number;
  onSuccess?: (response: TaskStatusResponse, taskId: string) => void;
  onFailure?: (response: TaskStatusResponse, taskId: string) => void;
  onError?: (error: Error, taskId: string) => void;
  onTimeout?: (taskId: string) => void;
};

export function useTaskPolling({
  token,
  buildStatusPath = (taskId) => `/documents/task-status/${taskId}`,
  intervalMs = 3000,
  timeoutMs = 300000,
  onSuccess,
  onFailure,
  onError,
  onTimeout,
}: UseTaskPollingOptions) {
  const [taskId, setTaskId] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) return;

    let cancelled = false;

    const checkStatus = async () => {
      try {
        const response = await apiRequest<TaskStatusResponse>(
          buildStatusPath(taskId),
          {
            token,
            errorMessage: "상태 조회에 실패했습니다.",
          },
        );

        if (cancelled) return;

        if (response.status === "SUCCESS") {
          onSuccess?.(response, taskId);
          setTaskId(null);
        } else if (response.status === "FAILURE") {
          onFailure?.(response, taskId);
          setTaskId(null);
        }
      } catch (err) {
        if (cancelled) return;
        onError?.(err instanceof Error ? err : new Error("폴링 오류"), taskId);
        setTaskId(null);
      }
    };

    checkStatus();
    const intervalId = setInterval(checkStatus, intervalMs);
    const timeoutId = setTimeout(() => {
      if (cancelled) return;
      onTimeout?.(taskId);
      setTaskId(null);
    }, timeoutMs);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
      clearTimeout(timeoutId);
    };
  }, [
    taskId,
    token,
    buildStatusPath,
    intervalMs,
    timeoutMs,
    onSuccess,
    onFailure,
    onError,
    onTimeout,
  ]);

  const startPolling = useCallback((nextTaskId: string) => {
    setTaskId(nextTaskId);
  }, []);

  const stopPolling = useCallback(() => setTaskId(null), []);

  return { startPolling, stopPolling, currentTaskId: taskId };
}
