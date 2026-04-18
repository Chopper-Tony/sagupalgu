import { useAuth } from "../contexts/AuthContext";
import "./UserMenu.css";

export function UserMenu() {
  const { user, configured, signOut } = useAuth();

  // Supabase 미설정 환경(dev bypass 등) 에서는 표시하지 않음
  if (!configured) return null;

  if (!user) {
    return (
      <a href="#/login" className="user-menu user-menu-login">
        로그인
      </a>
    );
  }

  const label = user.email ?? user.id.slice(0, 8);
  return (
    <div className="user-menu">
      <span className="user-menu-label" title={label}>
        {label}
      </span>
      <button
        type="button"
        className="user-menu-signout"
        onClick={() => {
          signOut().catch(() => {
            // 에러 무시 — 로컬 세션 정리만 원하면 새로고침
          });
        }}
      >
        로그아웃
      </button>
    </div>
  );
}
