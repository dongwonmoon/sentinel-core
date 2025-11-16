/**
 * @file React 애플리케이션의 메인 진입점(Entrypoint)입니다.
 * @description 이 파일은 React 애플리케이션을 초기화하고,
 * 루트 컴포넌트인 `<App />`을 public/index.html 파일의 'root' DOM 요소에 렌더링하는 역할을 합니다.
 */

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

// `public/index.html`에 정의된 'root' ID를 가진 DOM 요소를 찾습니다.
// 이 요소가 React 애플리케이션이 마운트될 컨테이너가 됩니다.
const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Failed to find the root element");
}

// React 18의 새로운 Concurrent Mode를 위한 루트를 생성합니다.
const root = ReactDOM.createRoot(rootElement);

// 애플리케이션의 루트 컴포넌트(<App />)를 렌더링합니다.
root.render(
  // React.StrictMode는 개발 모드에서 잠재적인 문제를 감지하고 경고를 표시하는 래퍼 컴포넌트입니다.
  // 예를 들어, 안전하지 않은 생명주기 메서드 사용, 레거시 API 사용 등에 대한 경고를 개발자에게 알려줍니다.
  // 프로덕션 빌드에서는 자동으로 비활성화되므로 성능에 영향을 주지 않습니다.
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
