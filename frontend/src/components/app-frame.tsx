import Link from "next/link";
import type { ReactNode } from "react";

const stages = [
  { label: "认证", href: "/", glyph: "认" },
  { label: "画像", href: "/profile", glyph: "像" },
  { label: "匹配", href: "/match", glyph: "遇" },
  { label: "互答", href: "/exchange", glyph: "答" },
] as const;

function getStageStatus(index: number, activeIndex: number) {
  if (index < activeIndex) return "已完成";
  if (index === activeIndex) return "当前";
  return "下一步";
}

export function AppFrame({
  active,
  children,
}: {
  active: (typeof stages)[number]["label"];
  children: ReactNode;
}) {
  const activeIndex = stages.findIndex((stage) => stage.label === active);

  return (
    <div className="app-frame">
      <header className="site-header">
        <Link className="wordmark" href="/" aria-label="Verso 首页">
          <span className="wordmark-leaf" aria-hidden="true" />
          <span>Verso</span>
          <small>背叶</small>
        </Link>

        <nav className="desktop-nav" aria-label="主流程">
          <ol className="stage-nav">
            {stages.map((stage) => (
              <li key={stage.label}>
                <Link
                  href={stage.href}
                  aria-current={active === stage.label ? "step" : undefined}
                >
                  <span aria-hidden="true">{stage.glyph}</span>
                  <span>{stage.label}</span>
                </Link>
              </li>
            ))}
          </ol>
        </nav>

        <span className="demo-chip">MVP 演示</span>
      </header>

      <aside className="side-rail" aria-label="Verso 导航">
        <Link
          className="wordmark side-wordmark"
          href="/"
          aria-label="Verso 首页"
        >
          <span className="wordmark-leaf" aria-hidden="true" />
          <span>Verso</span>
          <small>背叶</small>
        </Link>

        <nav aria-label="主流程">
          <ol className="side-stage-nav">
            {stages.map((stage, index) => (
              <li key={stage.label}>
                <Link
                  href={stage.href}
                  aria-current={active === stage.label ? "step" : undefined}
                >
                  <span className="nav-glyph" aria-hidden="true">
                    {stage.glyph}
                  </span>
                  <span>
                    <strong>{stage.label}</strong>
                    <small>{getStageStatus(index, activeIndex)}</small>
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        </nav>

        <div className="side-user">
          <span className="mini-avatar">林</span>
          <div>
            <strong>林屿</strong>
            <small>知乎身份已连接</small>
          </div>
          <span className="connection-dot" aria-label="连接正常" />
        </div>
      </aside>

      <div className="app-surface">{children}</div>

      <aside className="discovery-rail" aria-label="发现路径">
        <div className="discovery-heading">
          <span>发现路径</span>
          <strong>你想怎样遇见一个人？</strong>
        </div>

        <section className="path-card path-card-active">
          <div className="path-card-topline">
            <span className="path-orbit" aria-hidden="true">
              <i />
              <i />
            </span>
            <small>当前可用</small>
          </div>
          <h2>从一个问题出发</h2>
          <p>系统只在双方都能补上对方缺口时，把你们介绍给彼此。</p>
          <span className="path-status">双向互补匹配</span>
        </section>

        <section className="path-card path-card-future">
          <div className="article-stack" aria-hidden="true">
            <i />
            <i />
            <i />
          </div>
          <small>未来入口 · 设计占位</small>
          <h2>沿一篇文章相遇</h2>
          <p>
            为“人—文章—人”的发现方式保留位置；当前版本不参与匹配，也不新增接口。
          </p>
        </section>

        <p className="rail-note">
          先验证互补有没有价值，再让不同的相遇方式生长出来。
        </p>
      </aside>

      <nav className="mobile-tabbar" aria-label="主流程">
        {stages.map((stage) => (
          <Link
            key={stage.label}
            href={stage.href}
            aria-current={active === stage.label ? "step" : undefined}
          >
            <span aria-hidden="true">{stage.glyph}</span>
            {stage.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
