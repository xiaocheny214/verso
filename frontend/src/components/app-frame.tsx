import Link from "next/link";
import type { ReactNode } from "react";

const stages = [
  { label: "认证", href: "/" },
  { label: "画像", href: "/profile" },
  { label: "匹配", href: "/match" },
  { label: "互答", href: "/exchange" },
] as const;

export function AppFrame({
  active,
  children,
}: {
  active: (typeof stages)[number]["label"];
  children: ReactNode;
}) {
  return (
    <div className="app-frame">
      <header className="site-header">
        <Link className="wordmark" href="/" aria-label="Verso 首页">
          <span className="wordmark-leaf" aria-hidden="true" />
          <span>VERSO</span>
          <small>背叶</small>
        </Link>

        <nav aria-label="主流程">
          <ol className="stage-nav">
            {stages.map((stage, index) => (
              <li key={stage.label}>
                <Link
                  href={stage.href}
                  aria-current={active === stage.label ? "step" : undefined}
                >
                  <span>{index + 1}</span>
                  {stage.label}
                </Link>
              </li>
            ))}
          </ol>
        </nav>

        <span className="demo-chip">演示模式</span>
      </header>
      {children}
    </div>
  );
}
