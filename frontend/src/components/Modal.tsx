/**
 * @file 재사용 가능한 범용 모달(Modal) UI 컴포넌트입니다.
 * @description 이 컴포넌트는 화면 위에 새로운 레이어를 생성하여
 * 자식(children) 컴포넌트를 렌더링합니다. 배경을 어둡게 처리하고,
 * 'Escape' 키나 배경 클릭으로 닫는 기능을 제공합니다.
 */

import { CSSProperties, ReactNode, useEffect } from "react";

type Props = {
  /** 모달을 닫을 때 호출될 콜백 함수 */
  onClose: () => void;
  /** 모달의 열림/닫힘 상태. true일 때 모달이 표시됩니다. */
  isOpen?: boolean;
  /** 모달의 너비 (CSS 값) */
  width?: string;
  /** 모달의 최대 높이 (CSS 값) */
  maxHeight?: string;
  /** 모달 내부 컨텐츠 영역에 적용할 추가적인 CSS 스타일 */
  contentStyle?: CSSProperties;
  /** 모달 내부에 렌더링될 React 노드(컴포넌트, 엘리먼트 등) */
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
  // 모달이 열리거나 닫힐 때 부수 효과(Side Effect)를 처리하는 `useEffect` 훅입니다.
  useEffect(() => {
    // 모달이 닫혀 있으면 아무 작업도 하지 않습니다.
    if (!isOpen) return undefined;

    /** 'Escape' 키를 눌렀을 때 모달을 닫는 이벤트 핸들러입니다. */
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    // 모달이 열려 있는 동안 배경 페이지의 스크롤을 막기 위해
    // `document.body`의 overflow 스타일을 'hidden'으로 설정합니다.
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    
    // 'keydown' 이벤트를 window에 등록합니다.
    window.addEventListener("keydown", handleKey);

    // 컴포넌트가 언마운트되거나 `isOpen`이 false로 변경될 때 실행될 클린업(cleanup) 함수입니다.
    return () => {
      // 원래의 overflow 스타일로 복원합니다.
      document.body.style.overflow = originalOverflow;
      // 등록했던 이벤트 리스너를 제거하여 메모리 누수를 방지합니다.
      window.removeEventListener("keydown", handleKey);
    };
  }, [isOpen, onClose]); // `isOpen` 또는 `onClose`가 변경될 때마다 이 훅을 다시 실행합니다.

  if (!isOpen) {
    return null;
  }

  return (
    // 모달 오버레이: 배경을 어둡게 하고, 클릭 시 `onClose`를 호출하여 모달을 닫습니다.
    <div className="app-model-overlay" style={{ zIndex: 20 }} onClick={onClose}>
      {/* 
        모달 컨텐츠 영역: 실제 내용이 표시되는 부분입니다.
        `onClick` 이벤트에 `stopPropagation`을 호출하여,
        모달 내부를 클릭했을 때 오버레이의 `onClick`이 실행되어 모달이 닫히는 것을 방지합니다.
      */}
      <div
        className="app-model-content"
        style={{
          width,
          maxHeight,
          display: "flex",
          flexDirection: "column",
          ...contentStyle,
        }}
        onClick={(event) => event.stopPropagation()}
      >
        {/* 부모 컴포넌트로부터 전달받은 자식 요소들을 렌더링합니다. */}
        {children}
      </div>
    </div>
  );
}
