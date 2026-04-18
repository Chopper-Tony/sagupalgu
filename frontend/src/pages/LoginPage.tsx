import { useState, type FormEvent } from "react";
import { useAuth } from "../contexts/AuthContext";
import "./LoginPage.css";

type Mode = "signin" | "signup";

export function LoginPage() {
  const {
    configured,
    loading,
    signInWithPassword,
    signUpWithPassword,
    signInWithGoogle,
  } = useAuth();

  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!configured) {
      setError("Supabase 환경변수 미설정 — 운영자에게 문의하세요.");
      return;
    }
    setError(null);
    setInfo(null);
    setSubmitting(true);
    try {
      if (mode === "signin") {
        await signInWithPassword(email, password);
        // 로그인 성공 시 기본 화면으로 이동
        window.location.hash = "#/";
      } else {
        await signUpWithPassword(email, password);
        setInfo(
          "가입 요청이 접수됐습니다. 이메일 인증이 필요하면 메일함을 확인하세요.",
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const onGoogle = async () => {
    if (!configured) {
      setError("Supabase 환경변수 미설정 — 운영자에게 문의하세요.");
      return;
    }
    setError(null);
    try {
      await signInWithGoogle();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (loading) {
    return <div className="login-loading">로딩 중…</div>;
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <h1 className="login-title">사구팔구</h1>
        <p className="login-subtitle">
          {mode === "signin" ? "로그인" : "회원가입"}
        </p>

        {!configured && (
          <div className="login-message login-message-error">
            Supabase 미설정 환경입니다. dev 환경에서는 자동 인증으로 진입됩니다.
          </div>
        )}

        <form className="login-form" onSubmit={onSubmit}>
          <label className="login-field">
            <span>이메일</span>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={submitting}
            />
          </label>

          <label className="login-field">
            <span>비밀번호</span>
            <input
              type="password"
              required
              minLength={6}
              autoComplete={
                mode === "signin" ? "current-password" : "new-password"
              }
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
            />
          </label>

          <button
            type="submit"
            className="login-submit"
            disabled={submitting || !configured}
          >
            {submitting
              ? "처리 중…"
              : mode === "signin"
                ? "로그인"
                : "가입하기"}
          </button>
        </form>

        <div className="login-divider">또는</div>

        <button
          type="button"
          className="login-google"
          onClick={onGoogle}
          disabled={submitting || !configured}
        >
          Google로 계속하기
        </button>

        {error && (
          <div className="login-message login-message-error">{error}</div>
        )}
        {info && <div className="login-message login-message-info">{info}</div>}

        <button
          type="button"
          className="login-mode-toggle"
          onClick={() => {
            setMode(mode === "signin" ? "signup" : "signin");
            setError(null);
            setInfo(null);
          }}
        >
          {mode === "signin"
            ? "계정이 없으신가요? 회원가입"
            : "이미 계정이 있으신가요? 로그인"}
        </button>
      </div>
    </div>
  );
}
