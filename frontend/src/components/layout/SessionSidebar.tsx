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
  const [connectToken, setConnectToken] = useState<string | null>(null);
  const [tokenCopied, setTokenCopied] = useState(false);

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

  const handleGenerateToken = async () => {
    try {
      const result = await api.startPlatformConnect();
      setConnectToken(result.connect_token);
      setTokenCopied(false);
    } catch {
      alert("토큰 발급에 실패했습니다");
    }
  };

  const handleCopyToken = () => {
    if (!connectToken) return;
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(connectToken).catch(() => {
        fallbackCopy(connectToken);
      });
    } else {
      fallbackCopy(connectToken);
    }
    setTokenCopied(true);
    setTimeout(() => setTokenCopied(false), 3000);
  };

  function fallbackCopy(text: string) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }

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

        <div style={{ marginTop: "12px", borderTop: "1px solid #333", paddingTop: "10px" }}>
          <p style={{ fontSize: "11px", color: "#888", marginBottom: "6px" }}>
            크롬 익스텐션으로 연결
          </p>
          <button
            className="session-sidebar__platform-login-btn"
            onClick={handleGenerateToken}
            style={{ width: "100%", marginBottom: "6px" }}
          >
            연결 토큰 발급
          </button>
          {connectToken && (
            <div style={{ fontSize: "11px" }}>
              <input
                type="text"
                value={connectToken}
                readOnly
                style={{
                  width: "100%",
                  padding: "4px 6px",
                  background: "#16213e",
                  border: "1px solid #333",
                  borderRadius: "4px",
                  color: "#fff",
                  fontSize: "10px",
                  marginBottom: "4px",
                }}
              />
              <button
                onClick={handleCopyToken}
                style={{
                  width: "100%",
                  padding: "4px",
                  background: tokenCopied ? "#064e3b" : "#2563eb",
                  color: "#fff",
                  border: "none",
                  borderRadius: "4px",
                  cursor: "pointer",
                  fontSize: "11px",
                }}
              >
                {tokenCopied ? "복사됨!" : "토큰 복사"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
