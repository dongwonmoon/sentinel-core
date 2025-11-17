/**
 * @file 애플리케이션 전역에서 사용 가능한 간단한 '토스트(Toast)' 알림 시스템을 구현합니다.
 * @description 이 파일은 두 부분으로 구성됩니다:
 * 1. `NotificationHost` 컴포넌트: 실제 알림 UI를 렌더링하고 상태를 관리합니다.
 *    이 컴포넌트는 앱의 최상위 레이아웃에 한 번만 렌더링되어야 합니다.
 * 2. `notify` 함수: 애플리케이션의 어느 곳에서든 이 함수를 호출하여
 *    사용자에게 간단한 텍스트 알림을 띄울 수 있습니다.
 *
 * 이 방식은 React 컨텍스트(Context)나 다른 상태 관리 라이브러리 없이도
 * 전역 알림 기능을 구현하는 간단하고 효과적인 패턴입니다.
 */

import { useEffect, useState } from "react";

/** 개별 토스트 알림의 데이터 구조를 정의합니다. */
type Toast = {
  /** 고유 식별자 (컴포넌트 key로 사용) */
  id: number;
  /** 알림에 표시될 메시지 */
  message: string;
};

/**
 * `NotificationHost` 컴포넌트 내부의 상태 업데이트 함수를 가리키는 클로저(closure) 변수입니다.
 * 이 변수는 모듈 스코프에 존재하며, `NotificationHost`가 마운트될 때 실제 함수가 할당됩니다.
 */
let pushExternal: ((msg: string) => void) | null = null;

/**
 * 애플리케이션의 어느 곳에서든 토스트 알림을 띄우기 위해 호출하는 공개 함수입니다.
 * @param message 알림으로 표시할 텍스트 메시지
 */
export function notify(message: string) {
  // `pushExternal`에 함수가 할당되어 있을 경우 (즉, NotificationHost가 렌더링된 경우)에만 호출합니다.
  if (pushExternal) {
    pushExternal(message);
  }
}

/**
 * 화면에 토스트 알림들을 렌더링하는 '호스트' 컴포넌트입니다.
 * 이 컴포넌트는 앱 전체에 단 하나만 존재해야 합니다.
 */
export function NotificationHost() {
  // 현재 화면에 표시되고 있는 토스트 알림들의 목록을 관리하는 상태
  const [toasts, setToasts] = useState<Toast[]>([]);

  // 컴포넌트가 마운트될 때 `pushExternal` 함수를 설정하고,
  // 언마운트될 때 정리(cleanup)하는 `useEffect` 훅입니다.
  useEffect(() => {
    // `pushExternal`에 실제 상태 업데이트 로직을 할당합니다.
    pushExternal = (message: string) => {
      // 새 알림을 `toasts` 배열에 추가합니다.
      setToasts((current) => [...current, { id: Date.now(), message }]);
      
      // 3.5초 후에 가장 오래된 알림을 자동으로 제거합니다.
      setTimeout(() => {
        // `slice(1)`은 배열의 첫 번째 요소를 제외한 나머지를 반환하여,
        // 가장 먼저 추가된 알림을 제거하는 효과를 냅니다.
        setToasts((current) => current.slice(1));
      }, 3500);
    };

    // 컴포넌트가 언마운트될 때 실행될 클린업 함수입니다.
    return () => {
      // `pushExternal`을 null로 설정하여 메모리 누수를 방지하고,
      // 더 이상 존재하지 않는 컴포넌트의 상태를 업데이트하려는 시도를 막습니다.
      pushExternal = null;
    };
  }, []); // 빈 의존성 배열 `[]`은 이 훅이 컴포넌트 마운트 시 한 번만 실행되도록 합니다.

  return (
    // 알림들이 쌓일 컨테이너입니다. CSS를 통해 화면 우측 상단 등에 위치시킵니다.
    <div className="toast-stack">
      {toasts.map((toast) => (
        <div key={toast.id} className="toast">
          {toast.message}
        </div>
      ))}
    </div>
  );
}
