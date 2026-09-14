"use client";

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";

import { AppFrame } from "@/components/app-frame";
import { MatchExplanation } from "@/components/match-explanation";
import { demoMatch } from "@/lib/demo-data";

type MatchDemoState = "compose" | "waiting" | "matched" | "cancelled" | "error";

const stateLabels: Array<{ value: MatchDemoState; label: string }> = [
  { value: "compose", label: "填写" },
  { value: "waiting", label: "等待" },
  { value: "matched", label: "已匹配" },
  { value: "cancelled", label: "已取消" },
  { value: "error", label: "异常" },
];

function isMatchDemoState(value: string | null): value is MatchDemoState {
  return stateLabels.some((state) => state.value === value);
}

function subscribeToStaticRoute() {
  return () => undefined;
}

function getMatchRouteState(): MatchDemoState {
  const requested = new URLSearchParams(window.location.search).get("state");
  return isMatchDemoState(requested) ? requested : "compose";
}

const stateCopy: Record<
  MatchDemoState,
  { eyebrow: string; title: string; description: string }
> = {
  compose: {
    eyebrow: "一次问题，只参与一次匹配",
    title: "这一次，你想补上什么？",
    description:
      "写具体问题比选择兴趣标签更重要。它决定对方要为你留下什么答案。",
  },
  waiting: {
    eyebrow: "匹配条件已进入队列",
    title: "正在找能与你互补的人",
    description:
      "你可以先离开。只有两条 covers 关系同时成立时，我们才会打开交流。",
  },
  matched: {
    eyebrow: "双向互补成立",
    title: "两张背叶已经合上",
    description: "不是因为你们相似，而是因为双方都恰好能回答对方的问题。",
  },
  cancelled: {
    eyebrow: "本次 Ticket 已退出队列",
    title: "这次匹配已取消",
    description: "问题没有继续参与匹配，长期画像和知乎授权不会受到影响。",
  },
  error: {
    eyebrow: "提交没有完成",
    title: "问题还安全地留在这里",
    description: "网络暂时没有响应；你的输入没有丢失，也没有产生重复 Ticket。",
  },
};

const panelCopy = {
  waiting: {
    symbol: "···",
    status: "最长等待 24 小时",
    title: "",
  },
  cancelled: {
    symbol: "×",
    status: "没有产生交流关系",
    title: "想法变了，也可以随时重新开始。",
  },
  error: {
    symbol: "!",
    status: "可安全重试",
    title: "检查网络后再次提交；我们不会重复排队。",
  },
} as const;

export default function MatchPage() {
  const routeView = useSyncExternalStore<MatchDemoState>(
    subscribeToStaticRoute,
    getMatchRouteState,
    () => "compose",
  );
  const [selectedView, setView] = useState<MatchDemoState | null>(null);
  const view = selectedView ?? routeView;
  const [wantText, setWantText] = useState(demoMatch.want_text);
  const copy = stateCopy[view];
  const panel =
    view === "waiting" || view === "cancelled" || view === "error"
      ? panelCopy[view]
      : null;

  return (
    <AppFrame active="匹配">
      <main className="match-layout">
        <header className="match-heading">
          <p className="context-line">{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p>{copy.description}</p>
        </header>

        <div className="demo-state-rail" aria-label="演示匹配状态">
          <span>状态预览</span>
          {stateLabels.map((state) => (
            <button
              key={state.value}
              type="button"
              aria-pressed={view === state.value}
              onClick={() => setView(state.value)}
            >
              {state.label}
            </button>
          ))}
        </div>

        {view === "compose" && (
          <section className="ticket-composer" aria-labelledby="ticket-title">
            <div className="ticket-number">本次 Ticket</div>
            <div className="ticket-main">
              <label id="ticket-title" htmlFor="want-text">
                我想了解
              </label>
              <textarea
                id="want-text"
                value={wantText}
                onChange={(event) => setWantText(event.target.value)}
                maxLength={200}
              />
              <div className="ticket-meta">
                <label htmlFor="want-tag">归到能力方向</label>
                <select id="want-tag" defaultValue="健身">
                  <option>健身</option>
                  <option>训练</option>
                  <option>互联网</option>
                  <option>编程</option>
                  <option>写作</option>
                </select>
                <span>{wantText.length}/200</span>
              </div>
            </div>
            <button
              className="primary-action button-reset"
              type="button"
              disabled={!wantText.trim()}
              onClick={() => setView("waiting")}
            >
              提交本次问题
            </button>
          </section>
        )}

        {view === "matched" && (
          <>
            <MatchExplanation match={demoMatch} />
            <div className="match-actions">
              <button
                className="text-action button-reset"
                type="button"
                onClick={() => setView("compose")}
              >
                返回修改问题
              </button>
              <Link className="primary-action" href="/exchange">
                进入 24 小时互答
              </Link>
            </div>
          </>
        )}

        {panel && (
          <section
            className={`state-panel state-panel-${view}`}
            role={view === "error" ? "alert" : "status"}
          >
            <div className="state-symbol" aria-hidden="true">
              {panel.symbol}
            </div>
            <div>
              <span>{panel.status}</span>
              <h2>{view === "waiting" ? wantText : panel.title}</h2>
            </div>
            <div className="state-actions">
              {view === "waiting" ? (
                <>
                  <button
                    className="primary-action button-reset"
                    type="button"
                    onClick={() => setView("matched")}
                  >
                    演示找到互补对象
                  </button>
                  <button
                    className="text-action button-reset"
                    type="button"
                    onClick={() => setView("cancelled")}
                  >
                    取消这次匹配
                  </button>
                </>
              ) : (
                <button
                  className="primary-action button-reset"
                  type="button"
                  onClick={() => setView("compose")}
                >
                  {view === "cancelled" ? "重新填写问题" : "返回并重试"}
                </button>
              )}
            </div>
          </section>
        )}
      </main>
    </AppFrame>
  );
}
