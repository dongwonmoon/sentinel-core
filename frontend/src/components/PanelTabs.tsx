type Tab = {
  id: string;
  label: string;
};

type Props = {
  tabs: Tab[];
  activeId: string;
  onChange: (id: string) => void;
};

export default function PanelTabs({ tabs, activeId, onChange }: Props) {
  return (
    <div
      style={{
        display: "flex",
        borderBottom: "1px solid rgba(148, 163, 184, 0.15)",
      }}
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={tab.id === activeId ? "list-item active" : "list-item"}
          onClick={() => onChange(tab.id)}
          style={{ flex: 1, borderRadius: 0 }}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
