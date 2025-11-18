/**
 * @file Composer의 '+' 버튼 클릭 시 나타나는 팝오버 컴포넌트입니다.
 * @description 사용자에게 '파일 업로드' 또는 '코드 가져오기' 옵션을 제공합니다.
 */
import React from "react";

type Props = {
  /** '파일 업로드' 버튼 클릭 시 호출될 함수 */
  onFileUpload: () => void;
  /** '코드 가져오기' 버튼 클릭 시 호출될 함수 */
  onOpenCodeModal: () => void;
};

export default function UploadPopover({ onFileUpload, onOpenCodeModal }: Props) {
  return (
    <div className="upload-popover">
      <button className="list-item" onClick={onFileUpload}>
        <span style={{ fontSize: "1.2rem", marginRight: "1rem" }}>📎</span>
        파일 업로드
      </button>
      <button className="list-item" onClick={onOpenCodeModal}>
        <span style={{ fontSize: "1.2rem", marginRight: "1rem" }}>&lt;/&gt;</span>
        코드 가져오기
      </button>
    </div>
  );
}