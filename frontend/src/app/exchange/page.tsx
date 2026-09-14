"use client";

import { type FormEvent, useState, useSyncExternalStore } from "react";
import { Clock, Sparkles, Send, AlertCircle } from "lucide-react";

import { AppFrame } from "@/components/app-frame";
import type { ExchangeMessage } from "@/model/exchange";
import { demoMessages } from "@/model/exchange";
import { demoMatch } from "@/model/match";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";

type ExchangeDemoState = "open" | "empty" | "closed" | "error";

const exchangeStates: Array<{
  value: ExchangeDemoState;
  label: string;
}> = [
  { value: "open", label: "进行中" },
  { value: "empty", label: "等待回答" },
  { value: "closed", label: "已关闭" },
  { value: "error", label: "异常" },
];

function isExchangeDemoState(value: string | null): value is ExchangeDemoState {
  return exchangeStates.some((state) => state.value === value);
}

function subscribeToStaticRoute() {
  return () => undefined;
}

function getExchangeRouteState(): ExchangeDemoState {
  const requested = new URLSearchParams(window.location.search).get("state");
  return isExchangeDemoState(requested) ? requested : "open";
}

export default function ExchangePage() {
  const [messages, setMessages] = useState<ExchangeMessage[]>(demoMessages);
  const [draft, setDraft] = useState("");
  const routeView = useSyncExternalStore<ExchangeDemoState>(
    subscribeToStaticRoute,
    getExchangeRouteState,
    () => "open",
  );
  const [selectedView, setView] = useState<ExchangeDemoState | null>(null);
  const view = selectedView ?? routeView;
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
    <AppFrame>
      <div className="space-y-6">
        {/* Workspace Dual Layout: Left Sidebar (Sessions List) + Right Main (Workbench) */}
        <div className="grid lg:grid-cols-4 gap-6 items-start">
          {/* Left: SESSIONS LIST */}
          <aside className="lg:col-span-1 space-y-3">
            <div className="flex items-center justify-between px-1">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                对局列表 (1)
              </span>
            </div>

            <Card className="bg-white border-2 border-indigo-600 shadow-xs cursor-pointer">
              <CardContent className="p-4 space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-100 text-emerald-800 font-bold text-xs">
                      周
                    </div>
                    <div>
                      <span className="text-xs font-bold text-slate-900 block">
                        周衡
                      </span>
                      <span className="text-[10px] text-slate-400 block">
                        健身 ⇄ 互联网
                      </span>
                    </div>
                  </div>
                  <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                </div>

                <div className="text-[11px] text-slate-600 line-clamp-2 bg-slate-50 p-2 rounded">
                  求教：{demoMatch.want_text}
                </div>

                <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-100">
                  <span>{view === "closed" ? "已结束" : "剩余 21:34"}</span>
                  <span className="text-indigo-600 font-semibold">
                    当前对局
                  </span>
                </div>
              </CardContent>
            </Card>
          </aside>

          {/* Right: MAIN WORKBENCH */}
          <div className="lg:col-span-3 space-y-6">
            {/* Session Top Bar with State Preview */}
            <Card className="bg-white border-slate-200">
              <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-slate-900">
                      与 {peer.name} 的互答对局
                    </span>
                    <Badge
                      variant="secondary"
                      className={
                        view === "closed"
                          ? "text-slate-600 bg-slate-100"
                          : "text-emerald-700 bg-emerald-50 border-emerald-200"
                      }
                    >
                      {view === "closed" ? "已归档" : "24h 互答中"}
                    </Badge>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5 text-xs text-slate-500">
                    <Clock className="h-3.5 w-3.5 text-indigo-600" />
                    <span className="font-semibold">
                      {view === "closed" ? "已归档" : "剩余 21:34"}
                    </span>
                  </div>

                  {/* State switcher */}
                  <div className="flex items-center gap-1 pl-3 border-l border-slate-200">
                    {exchangeStates.map((state) => (
                      <Button
                        key={state.value}
                        type="button"
                        variant={view === state.value ? "default" : "outline"}
                        size="xs"
                        onClick={() => setView(state.value)}
                        className="text-[11px] h-6 px-2"
                      >
                        {state.label}
                      </Button>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Error view */}
            {view === "error" && (
              <Card className="bg-white border-rose-200">
                <CardContent className="p-8 text-center space-y-3">
                  <AlertCircle className="h-7 w-7 text-rose-500 mx-auto" />
                  <h3 className="text-sm font-bold text-slate-900">
                    网络连接中断
                  </h3>
                  <p className="text-xs text-slate-400">
                    本地草稿未丢失，网络恢复后可继续作答。
                  </p>
                  <Button size="sm" onClick={() => setView("open")}>
                    重新载入
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* Dual Lanes */}
            {view !== "error" && (
              <div className="grid md:grid-cols-2 gap-6 items-start">
                {/* Peer's Answer to Me */}
                <Card className="bg-white border-slate-200 flex flex-col min-h-[440px]">
                  <CardHeader className="pb-3 border-b border-slate-100 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-800">
                        {peer.name} 正在回答你的问题
                      </span>
                      <Badge
                        variant="outline"
                        className="text-emerald-700 bg-emerald-50 border-emerald-200 text-[10px]"
                      >
                        健身
                      </Badge>
                    </div>
                    <div className="text-xs text-slate-900 font-semibold bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                      {demoMatch.want_text}
                    </div>
                  </CardHeader>

                  <CardContent className="py-4 space-y-3 flex-1 overflow-y-auto">
                    {visibleMessages
                      .filter((m) => m.sender_id === peer.id)
                      .map((m) => (
                        <div
                          key={m.id}
                          className="p-3.5 rounded-lg bg-emerald-50/60 border border-emerald-100 text-xs text-slate-800 leading-relaxed space-y-1.5"
                        >
                          <p>{m.text}</p>
                          <div className="text-[10px] text-emerald-700 font-medium">
                            {peer.name} · 今天 19:08
                          </div>
                        </div>
                      ))}

                    {view === "empty" && (
                      <div className="py-12 text-center text-xs text-slate-400">
                        对方正在组织答案，请稍候。
                      </div>
                    )}
                  </CardContent>

                  <div className="p-4 pt-3 border-t border-slate-100 text-[11px] text-slate-400 flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-indigo-600 shrink-0" />
                    <span>收到完整方案后，由系统 AI 提供质量复核</span>
                  </div>
                </Card>

                {/* My Answer to Peer */}
                <Card className="bg-white border-slate-200 flex flex-col min-h-[440px]">
                  <CardHeader className="pb-3 border-b border-slate-100 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-800">
                        你正在回答 {peer.name} 的问题
                      </span>
                      <Badge
                        variant="outline"
                        className="text-indigo-700 bg-indigo-50 border-indigo-200 text-[10px]"
                      >
                        互联网
                      </Badge>
                    </div>
                    <div className="text-xs text-slate-900 font-semibold bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                      {peer.want_text}
                    </div>
                  </CardHeader>

                  <CardContent className="py-4 space-y-3 flex-1 overflow-y-auto">
                    {visibleMessages
                      .filter((m) => m.sender_id === "user-linyu")
                      .map((m) => (
                        <div
                          key={m.id}
                          className="p-3.5 rounded-lg bg-indigo-50/60 border border-indigo-100 text-xs text-slate-800 leading-relaxed space-y-1.5"
                        >
                          <p>{m.text}</p>
                          <div className="text-[10px] text-indigo-700 font-medium">
                            你 ·{" "}
                            {m.id.startsWith("demo-") ? "刚刚" : "今天 19:24"}
                          </div>
                        </div>
                      ))}

                    {view === "empty" && (
                      <div className="py-12 text-center text-xs text-slate-400">
                        留下你的第一条针对性建议。
                      </div>
                    )}
                  </CardContent>

                  {view === "closed" ? (
                    <div className="p-4 pt-3 border-t border-slate-100 text-center space-y-1 text-xs">
                      <span className="font-bold text-slate-600 block">
                        本轮对局已归档
                      </span>
                      <p className="text-slate-400 text-[11px]">
                        答案已保留。若需新的解答，请发起新匹配。
                      </p>
                    </div>
                  ) : (
                    <form
                      onSubmit={send}
                      className="p-4 pt-3 border-t border-slate-100 space-y-2.5"
                    >
                      <label
                        htmlFor="answer"
                        className="block text-xs font-bold text-slate-700"
                      >
                        继续补充你的回答:
                      </label>
                      <Textarea
                        id="answer"
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        placeholder="提供一个具体、可执行的回答……"
                        maxLength={2000}
                        rows={3}
                        className="resize-none text-xs"
                      />
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] text-slate-400">
                          {draft.length} / 2000 字
                        </span>
                        <Button
                          type="submit"
                          size="sm"
                          disabled={!draft.trim()}
                          className="gap-1.5"
                        >
                          <Send className="h-3 w-3" />
                          <span>发送回答</span>
                        </Button>
                      </div>
                    </form>
                  )}
                </Card>
              </div>
            )}
          </div>
        </div>
      </div>
    </AppFrame>
  );
}
