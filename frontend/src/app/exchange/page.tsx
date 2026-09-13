"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";

import { AppFrame } from "@/components/app-frame";
import type { ExchangeMessage } from "@/lib/contracts";
import { demoMatch, demoMessages } from "@/lib/demo-data";

type ExchangeDemoState = "open" | "empty" | "closed" | "error";

const exchangeStates: Array<{ value: ExchangeDemoState; label: string }> = [
  { value: "open", label: "进行中" },
  { value: "empty", label: "暂无回答" },
  { value: "closed", label: "已关闭" },
  { value: "error", label: "异常" },
];

const exchangeTitles: Record<ExchangeDemoState, string> = {
  open: "这不是闲聊，每个人带走一个答案。",
  empty: "这不是闲聊，每个人带走一个答案。",
  closed: "这一轮已经收束，答案仍然留在这里。",
  error: "回答暂时没有同步过来。",
};

export default function ExchangePage() {
  const [messages, setMessages] = useState(demoMessages);
  const [draft, setDraft] = useState("");
  const [view, setView] = useState<ExchangeDemoState>("open");
  const peer = demoMatch.peer!;
  const visibleMessages = view === "empty" ? [] : messages;

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    const message: ExchangeMessage = {
      id: `demo-${messages.length + 1}`,
      exchange_id: demoMatch.pair_id!,
      sender_id: "user-linyu",
      text,
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, message]);
    setDraft("");
  }

  return (
    <AppFrame active="互答">
      <main className="exchange-layout">
        <header className="exchange-heading">
          <div>
            <p className="context-line">异步互答 · 双方随时回来继续</p>
            <h1>{exchangeTitles[view]}</h1>
          </div>
          <div className="timebox">
            <span>{view === "closed" ? "本轮状态" : "剩余时间"}</span>
            <strong>{view === "closed" ? "已关闭" : "21:34"}</strong>
            <small>
              {view === "closed" ? "仍可回看双方答案" : "明日 20:00 自动关闭"}
            </small>
          </div>
        </header>

        <div className="demo-state-rail" aria-label="演示互答状态">
          <span>状态预览</span>
          {exchangeStates.map((state) => (
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

        {view === "error" ? (
          <section className="state-panel state-panel-error" role="alert">
            <div className="state-symbol" aria-hidden="true">
              !
            </div>
            <div>
              <span>本地草稿没有丢失</span>
              <h2>网络恢复后再同步，不会重复发送回答。</h2>
            </div>
            <div className="state-actions">
              <button
                className="primary-action button-reset"
                type="button"
                onClick={() => setView("open")}
              >
                重新载入交流
              </button>
            </div>
          </section>
        ) : (
          <section className={`answer-board answer-board-${view}`}>
            <article className="answer-lane answer-lane-peer">
              <header>
                <span className="mini-avatar">周</span>
                <div>
                  <small>{peer.name} 正在回答你的问题</small>
                  <h2>{demoMatch.want_text}</h2>
                </div>
              </header>
              <div className="answer-stream">
                {visibleMessages
                  .filter((message) => message.sender_id === peer.id)
                  .map((message) => (
                    <blockquote key={message.id}>
                      <p>{message.text}</p>
                      <time>今天 19:08</time>
                    </blockquote>
                  ))}
                {view === "empty" ? (
                  <p className="empty-answer">对方还没有留下第一条回答。</p>
                ) : null}
              </div>
              <div className="quality-line">
                <span>等你判断</span>
                收到完整答案后，再决定是否交给 AI 复核质量
              </div>
            </article>

            <article className="answer-lane answer-lane-me">
              <header>
                <span className="mini-avatar">林</span>
                <div>
                  <small>你正在回答 {peer.name} 的问题</small>
                  <h2>{peer.want_text}</h2>
                </div>
              </header>
              <div className="answer-stream">
                {visibleMessages
                  .filter((message) => message.sender_id === "user-linyu")
                  .map((message) => (
                    <blockquote key={message.id}>
                      <p>{message.text}</p>
                      <time>
                        {message.id.startsWith("demo-") ? "刚刚" : "今天 19:24"}
                      </time>
                    </blockquote>
                  ))}
                {view === "empty" ? (
                  <p className="empty-answer">
                    从一个具体建议开始，不需要一次写完。
                  </p>
                ) : null}
              </div>
              {view === "closed" ? (
                <div className="closed-note">
                  <span>交流窗口已关闭</span>
                  <p>双方答案已保留；需要新的帮助时，请提交一个新的问题。</p>
                  <Link className="text-action" href="/match">
                    发起新的匹配
                  </Link>
                </div>
              ) : (
                <form className="answer-composer" onSubmit={send}>
                  <label htmlFor="answer">继续补充你的答案</label>
                  <textarea
                    id="answer"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder="给一个具体、能执行的回答……"
                    maxLength={2000}
                  />
                  <div>
                    <span>{draft.length}/2000</span>
                    <button
                      className="primary-action button-reset"
                      type="submit"
                      disabled={!draft.trim()}
                    >
                      留下回答
                    </button>
                  </div>
                </form>
              )}
            </article>
          </section>
        )}
      </main>
    </AppFrame>
  );
}
