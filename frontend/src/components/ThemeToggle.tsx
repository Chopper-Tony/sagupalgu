import { useState, useEffect } from "react";

function getInitialTheme(): "light" | "dark" {
  const stored = localStorage.getItem("sagupalgu_theme");
  if (stored === "dark" || stored === "light") return stored;
  return "light";
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("sagupalgu_theme", theme);
  }, [theme]);

  // 초기 로드 시 테마 적용
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", getInitialTheme());
  }, []);

  return (
    <button
      onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
      style={{
        position: "fixed",
        top: 12,
        right: 12,
        zIndex: 9999,
        padding: "6px 12px",
        borderRadius: 6,
        border: "1px solid var(--border)",
        background: "var(--bg-secondary)",
        color: "var(--text-primary)",
        cursor: "pointer",
        fontSize: 13,
        fontWeight: 500,
      }}
      title={theme === "light" ? "다크 모드로 전환" : "라이트 모드로 전환"}
    >
      {theme === "light" ? "Dark" : "Light"}
    </button>
  );
}
