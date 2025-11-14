import { useEffect, useState } from "react";

type Toast = { id: number; message: string };

let pushExternal: ((msg: string) => void) | null = null;

export function notify(message: string) {
  if (pushExternal) pushExternal(message);
}

export function NotificationHost() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    pushExternal = (message: string) => {
      setToasts((current) => [...current, { id: Date.now(), message }]);
      setTimeout(() => {
        setToasts((current) => current.slice(1));
      }, 3500);
    };
    return () => {
      pushExternal = null;
    };
  }, []);

  return (
    <div className="toast-stack">
      {toasts.map((toast) => (
        <div key={toast.id} className="toast">
          {toast.message}
        </div>
      ))}
    </div>
  );
}
