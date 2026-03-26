import { useState, useEffect } from "react";
import { api } from "../../lib/api";
import "./SessionSidebar.css";

interface Session {
  id: string;
  label: string;
  status: string;
}

interface PlatformInfo {
  name: string;
  connected: boolean;
  session_saved_at: string | null;
}

interface SessionSidebarProps {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

export function SessionSidebar({ sessions, activeId, onSelect, onNew }: SessionSidebarProps) {
  const [platforms, setPlatforms] = useState<Record<string, PlatformInfo>>({});
  const [loginLoading, setLoginLoading] = useState<string | null>(null);

  useEffect(() => {
    api.getPlatformStatus()
      .then((data) => setPlatforms(data.platforms))
      .catch(() => {});
  }, []);

  const handleLogin = async (platform: string) => {
    setLoginLoading(platform);
    try {
      const result = await api.platformLogin(platform);
      if (result.success) {
        // 상태 갱신
        const updated = await api.getPlatformStatus();
        setPlatforms(updated.platforms);
      } else {
        alert(result.error || "로그인에 실패했습니다");
      }
    } catch {
      alert("로그인 중 오류가 발생했습니다");
    } finally {
      setLoginLoading(null);
    }
  };

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

      <div className="session-sidebar__platforms">
        <p className="session-sidebar__platforms-title">플랫폼 연동</p>
        {Object.entries(platforms).map(([key, info]) => (
          <div key={key} className="session-sidebar__platform-item">
            <span className="session-sidebar__platform-name">
              {info.connected ? "✅" : "⚪"} {info.name}
            </span>
            {info.connected ? (
              <>
                <span className="session-sidebar__platform-status">연동됨</span>
                <button
                  className="session-sidebar__platform-relogin-btn"
                  onClick={() => handleLogin(key)}
                  disabled={loginLoading !== null}
                >
                  {loginLoading === key ? "로그인 중..." : "재로그인"}
                </button>
              </>
            ) : (
              <button
                className="session-sidebar__platform-login-btn"
                onClick={() => handleLogin(key)}
                disabled={loginLoading !== null}
              >
                {loginLoading === key ? "로그인 중..." : "로그인"}
              </button>
            )}
          </div>
        ))}
        {Object.keys(platforms).length === 0 && (
          <p className="session-sidebar__platform-empty">로딩 중...</p>
        )}
      </div>
    </div>
  );
}
