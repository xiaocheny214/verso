"use client";

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import { ArrowRight, RefreshCw, AlertCircle, XCircle } from "lucide-react";

import { AppFrame } from "@/components/app-frame";
import { MatchExplanation } from "@/components/match-explanation";
import { demoMatch } from "@/model/match";
import type { StrengthTag } from "@/model/portrait";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "cn";

type MatchDemoState = "compose" | "waiting" | "matched" | "cancelled" | "error";

const stateLabels: Array<{
  value: MatchDemoState;
  label: string;
}> = [
  { value: "compose", label: "填写需求" },
  { value: "waiting", label: "匹配中" },
  { value: "matched", label: "匹配成功" },
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

export default function MatchPage() {
  const routeView = useSyncExternalStore<MatchDemoState>(
    subscribeToStaticRoute,
    getMatchRouteState,
    () => "compose",
  );
  const [selectedView, setView] = useState<MatchDemoState | null>(null);
  const view = selectedView ?? routeView;
  const [wantText, setWantText] = useState(demoMatch.want_text);
  const [wantTag, setWantTag] = useState(demoMatch.want_tag);

  return (
    <AppFrame>
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Status switcher for preview */}
        <div className="flex items-center justify-between pb-2 border-b border-slate-200">
          <span className="text-xs font-semibold text-slate-500">
            状态切换预览:
          </span>
          <div className="flex items-center gap-1.5 text-xs">
            {stateLabels.map((state) => (
              <Button
                key={state.value}
                type="button"
                variant={view === state.value ? "default" : "outline"}
                size="sm"
                onClick={() => setView(state.value)}
                className="h-7 text-xs px-2.5"
              >
                {state.label}
              </Button>
            ))}
          </div>
        </div>

        {/* 1. COMPOSE */}
        {view === "compose" && (
          <Card className="bg-white border-slate-200">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-bold text-slate-900">
                发起单次互补需求
              </CardTitle>
            </CardHeader>

            <CardContent className="space-y-4">
              <div>
                <label
                  htmlFor="want-text"
                  className="block text-xs font-bold text-slate-700 mb-1"
                >
                  具体想了解的问题
                </label>
                <Textarea
                  id="want-text"
                  value={wantText}
                  onChange={(e) => setWantText(e.target.value)}
                  maxLength={200}
                  rows={4}
                  placeholder="例如：没有器械，怎样制定一套能坚持三个月的力量训练计划？"
                  className="resize-none"
                />
                <div className="flex justify-between text-xs text-slate-400 mt-1">
                  <span>建议交代具体背景与目标</span>
                  <span>{wantText.length} / 200 字</span>
                </div>
              </div>

              <div className="grid sm:grid-cols-2 gap-4 pt-1">
                <div>
                  <label
                    htmlFor="want-tag"
                    className="block text-xs font-bold text-slate-700 mb-1"
                  >
                    期望对方能力方向
                  </label>
                  <select
                    id="want-tag"
                    value={wantTag}
                    onChange={(e) => setWantTag(e.target.value as StrengthTag)}
                    className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-800 bg-white"
                  >
                    <option value="健身">健身 & 训练计划</option>
                    <option value="训练">力量与体态指导</option>
                    <option value="互联网">互联网 & 产品思维</option>
                    <option value="编程">编程与工程架构</option>
                    <option value="写作">内容表达与写作</option>
                  </select>
                </div>

                <div className="p-3 rounded-lg bg-slate-50 border border-slate-100 text-xs text-slate-500 flex flex-col justify-center">
                  <span className="font-semibold text-slate-700">
                    你的提供能力：互联网 · 编程
                  </span>
                  <span className="text-slate-400 text-[11px] mt-0.5">
                    来自画像，系统将自动寻找互补伙伴
                  </span>
                </div>
              </div>

              <div className="pt-4 border-t border-slate-100 flex justify-end">
                <Button
                  type="button"
                  disabled={!wantText.trim()}
                  onClick={() => setView("waiting")}
                >
                  提交问题进入队列
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* 2. MATCHED */}
        {view === "matched" && (
          <Card className="bg-white border-slate-200">
            <CardHeader className="pb-3 flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base font-bold text-slate-900">
                双向互补匹配成功
              </CardTitle>
              <Badge variant="secondary" className="text-emerald-700 bg-emerald-50 border-emerald-200">
                对局就绪
              </Badge>
            </CardHeader>

            <CardContent className="space-y-6">
              <MatchExplanation match={demoMatch} />

              <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setView("compose")}
                >
                  修改问题
                </Button>
                <Link
                  href="/exchange"
                  className={cn(buttonVariants({ size: "sm" }), "gap-1.5")}
                >
                  <span>进入翻开的叶（对局互答）</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            </CardContent>
          </Card>
        )}

        {/* 3. WAITING */}
        {view === "waiting" && (
          <Card className="bg-white border-slate-200">
            <CardContent className="p-8 text-center space-y-4">
              <RefreshCw className="h-8 w-8 animate-spin text-indigo-600 mx-auto" />
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  “{wantText}”
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  正在全网创作者画像中寻找互补伙伴。双方均满足条件时开启对局。
                </p>
              </div>
              <div className="flex justify-center gap-2 pt-2">
                <Button size="sm" onClick={() => setView("matched")}>
                  模拟匹配成功
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setView("cancelled")}
                >
                  取消匹配
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* 4. CANCELLED */}
        {view === "cancelled" && (
          <Card className="bg-white border-slate-200">
            <CardContent className="p-8 text-center space-y-4">
              <XCircle className="h-8 w-8 text-slate-400 mx-auto" />
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  匹配已取消
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  需求已撤回，长期画像不受影响。
                </p>
              </div>
              <Button size="sm" onClick={() => setView("compose")}>
                重新填写
              </Button>
            </CardContent>
          </Card>
        )}

        {/* 5. ERROR */}
        {view === "error" && (
          <Card className="bg-white border-rose-200">
            <CardContent className="p-8 text-center space-y-4">
              <AlertCircle className="h-8 w-8 text-rose-500 mx-auto" />
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  网络连接暂时异常
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  草稿仍在本地，未发生重复提交。
                </p>
              </div>
              <Button size="sm" onClick={() => setView("compose")}>
                重试
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </AppFrame>
  );
}
