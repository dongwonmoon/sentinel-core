import { useEffect, useRef, useState } from "react";

type Command = {
  id: string;
  label: string;
  action: () => void;
};

type Props = {
  isOpen: boolean;
  onClose: () => void;
  commands: Command[];
};

export default function CommandPalette({ isOpen, onClose, commands }: Props) {
  const [searchTerm, setSearchTerm] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const filteredCommands = commands.filter((cmd) =>
    cmd.label.toLowerCase().includes(searchTerm.toLowerCase()),
  );

  const handleCommandClick = (command: Command) => {
    command.action();
    onClose();
  };

  return (
    <div className="command-palette-overlay" onClick={onClose}>
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
            <p className="muted" style={{ textAlign: "center", padding: "1rem" }}>
              일치하는 명령어가 없습니다.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}