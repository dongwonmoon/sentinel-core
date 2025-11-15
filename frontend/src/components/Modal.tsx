import { CSSProperties, ReactNode, useEffect } from "react";

type Props = {
  onClose: () => void;
  isOpen?: boolean;
  width?: string;
  maxHeight?: string;
  contentStyle?: CSSProperties;
  children: ReactNode;
};

export default function Modal({
  onClose,
  isOpen = true,
  width = "min(500px, 90vw)",
  maxHeight = "70vh",
  contentStyle,
  children,
}: Props) {
  useEffect(() => {
    if (!isOpen) return undefined;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKey);
    return () => {
      document.body.style.overflow = originalOverflow;
      window.removeEventListener("keydown", handleKey);
    };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    <div className="auth-wrapper" style={{ zIndex: 20 }} onClick={onClose}>
      <div
        className="auth-card"
        style={{
          width,
          maxHeight,
          display: "flex",
          flexDirection: "column",
          ...contentStyle,
        }}
        onClick={(event) => event.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
