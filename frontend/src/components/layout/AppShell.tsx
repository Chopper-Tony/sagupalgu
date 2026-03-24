import type { ReactNode } from "react";
import "./AppShell.css";

interface AppShellProps {
  sidebar: ReactNode;
  main: ReactNode;
}

export function AppShell({ sidebar, main }: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className="app-shell__sidebar">{sidebar}</aside>
      <main className="app-shell__main">{main}</main>
    </div>
  );
}
