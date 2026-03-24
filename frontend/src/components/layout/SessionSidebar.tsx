import "./SessionSidebar.css";

interface Session {
  id: string;
  label: string;
  status: string;
}

interface SessionSidebarProps {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

export function SessionSidebar({ sessions, activeId, onSelect, onNew }: SessionSidebarProps) {
  return (
    <div className="session-sidebar">
      <div className="session-sidebar__header">
        <span className="session-sidebar__title">사구팔구</span>
        <button className="session-sidebar__new-btn" onClick={onNew}>
          + 새 판매
        </button>
      </div>
      <ul className="session-sidebar__list">
        {sessions.map((s) => (
          <li
            key={s.id}
            className={`session-sidebar__item${s.id === activeId ? " session-sidebar__item--active" : ""}`}
            onClick={() => onSelect(s.id)}
          >
            <span className="session-sidebar__item-label">{s.label}</span>
            <span className="session-sidebar__item-status">{s.status}</span>
          </li>
        ))}
        {sessions.length === 0 && (
          <li className="session-sidebar__empty">세션이 없습니다</li>
        )}
      </ul>
    </div>
  );
}
