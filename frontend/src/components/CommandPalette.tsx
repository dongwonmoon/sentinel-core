/**
 * @file '명령어 팔레트(Command Palette)' UI 컴포넌트입니다.
 * @description VS Code의 `Ctrl+Shift+P`와 유사한 기능으로,
 * 사용자에게 검색 가능한 명령어 목록을 제공하고, 선택된 명령어를 실행하는
 * 모달(Modal) 형태의 인터페이스입니다.
 */

import { useEffect, useRef, useState } from "react";

/** 명령어 팔레트에 표시될 개별 명령어의 구조를 정의합니다. */
type Command = {
  /** 명령어의 고유 식별자 */
  id: string;
  /** UI에 표시될 명령어의 이름 (예: "로그아웃") */
  label: string;
  /** 이 명령어가 선택되었을 때 실행될 함수 */
  action: () => void;
};

/** CommandPalette 컴포넌트가 받는 props의 타입을 정의합니다. */
type Props = {
  /** 팔레트의 열림/닫힘 상태 */
  isOpen: boolean;
  /** 팔레트를 닫을 때 호출될 콜백 함수 */
  onClose: () => void;
  /** 팔레트에 표시될 전체 명령어 목록 */
  commands: Command[];
};

export default function CommandPalette({ isOpen, onClose, commands }: Props) {

  // 사용자가 입력하는 검색어를 관리하는 상태

  const [searchTerm, setSearchTerm] = useState("");

  // 입력(input) 필드에 대한 참조(reference)를 생성합니다.

  const inputRef = useRef<HTMLInputElement>(null);



  // `isOpen` 상태가 변경될 때마다 실행되는 Effect 훅입니다.

  useEffect(() => {

    // 팔레트가 열릴 때, 입력 필드에 자동으로 포커스를 맞춥니다.

    if (isOpen) {

      inputRef.current?.focus();

    }

  }, [isOpen]);



  // 팔레트가 닫혀 있으면 아무것도 렌더링하지 않습니다.

  if (!isOpen) return null;



  // 검색어(`searchTerm`)를 기반으로 전체 명령어 목록(`commands`)을 필터링합니다.

  const filteredCommands = commands.filter((cmd) =>

    cmd.label.toLowerCase().includes(searchTerm.toLowerCase()),

  );



  /**

   * 사용자가 특정 명령어를 클릭했을 때 호출되는 핸들러입니다.

   * @param command 클릭된 명령어 객체

   */

  const handleCommandClick = (command: Command) => {

    command.action(); // 명령어에 연결된 실제 동작을 실행합니다.

    onClose(); // 명령 실행 후 팔레트를 닫습니다.

  };



  return (

    // 오버레이: 팔레트 뒤의 배경을 어둡게 하고, 클릭 시 팔레트를 닫는 역할을 합니다.

    <div className="command-palette-overlay" onClick={onClose}>

      {/* 모달: 실제 명령어 팔레트 UI 부분입니다.

          오버레이의 클릭 이벤트가 모달 내부로 전파되는 것을 막습니다. (e.stopPropagation) */}

      <div className="command-palette-modal" onClick={(e) => e.stopPropagation()}>

        <input

          ref={inputRef}

          type="text"

          placeholder="명령어를 입력하세요..."

          value={searchTerm}

          onChange={(e) => setSearchTerm(e.target.value)}

          className="command-palette-input"

        />

        <div className="command-list">

          {filteredCommands.length > 0 ? (

            // 필터링된 명령어를 목록으로 렌더링합니다.

            filteredCommands.map((cmd) => (

              <button

                key={cmd.id}

                className="command-item"

                onClick={() => handleCommandClick(cmd)}

              >

                {cmd.label}

              </button>

            ))

          ) : (

            // 일치하는 명령어가 없을 경우 메시지를 표시합니다.

            <p className="muted" style={{ textAlign: "center", padding: "1rem" }}>

              일치하는 명령어가 없습니다.

            </p>

          )}

        </div>

      </div>

    </div>

  );

}
