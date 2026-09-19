"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, RefreshCw, AlertCircle, XCircle } from "lucide-react";

import { AppFrame } from "@/components/app-frame";
import { MatchExplanation } from "@/components/match-explanation";
import { RequireSession } from "@/components/require-session";
import { useSession } from "@/components/use-session";
import { isMatchIneligible, matchQueryKey, ticketApi } from "@/model/match";
import { STRENGTH_TAGS } from "@/model/portrait";
import type { StrengthTag } from "@/model/portrait";
import { ApiError, isUnauthenticated } from "@/lib/http";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "cn";

const WAITING_POLL_MS = 5000;

function formatExpiry(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function MatchPageContent() {
  const queryClient = useQueryClient();
  const session = useSession();

  const [wantText, setWantText] = useState("");
  const [wantTag, setWantTag] = useState<StrengthTag | "">("");
  const [justCancelled, setJustCancelled] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const matchQuery = useQuery({
    queryKey: matchQueryKey,
    queryFn: ticketApi.currentMatch,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.status === "waiting" ? WAITING_POLL_MS : false,
  });

  const myStrengths = useMemo(() => {
    const tags = new Set<StrengthTag>();
    for (const portrait of session.user?.portraits ?? []) {
      for (const strength of portrait.strengths ?? []) {
        tags.add(strength.tag);
      }
    }
    return [...tags];
  }, [session.user]);

  const submitMutation = useMutation({
    mutationFn: () => {
      if (wantTag === "") {
        throw new ApiError(400, "请选择期望的能力方向");
      }
      return ticketApi.submitMatch(wantText.trim(), wantTag);
    },
    onSuccess: (match) => {
      setSubmitError(null);
      setJustCancelled(false);
      queryClient.setQueryData(matchQueryKey, match);
    },
    onError: (error) => {
      if (isMatchIneligible(error)) {
        setBlocked(true);
        return;
      }
      if (error instanceof ApiError && error.code === 409) {
        void queryClient.invalidateQueries({ queryKey: matchQueryKey });
        return;
      }
      if (isUnauthenticated(error)) {
        setSubmitError("请先用知乎账号登录，再发起匹配");
        return;
      }
      setSubmitError(error instanceof Error ? error.message : "提交失败");
    },
  });

  const cancelMutation = useMutation({
    mutationFn: ticketApi.cancelMatch,
    onSuccess: () => {
      setJustCancelled(true);
      queryClient.setQueryData(matchQueryKey, null);
    },
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: matchQueryKey });
    },
  });

  if (matchQuery.isPending) {
    return (
      <AppFrame>
        <Card className="bg-white border-slate-200">
          <CardContent className="p-8 text-center space-y-3">
            <RefreshCw className="h-7 w-7 animate-spin text-indigo-600 mx-auto" />
            <p className="text-sm text-slate-500">正在读取匹配状态…</p>
          </CardContent>
        </Card>
      </AppFrame>
    );
  }

  if (matchQuery.isError) {
    return (
      <AppFrame>
        <Card className="bg-white border-rose-200">
          <CardContent className="p-8 text-center space-y-4">
            <AlertCircle className="h-8 w-8 text-rose-500 mx-auto" />
            <div>
              <h3 className="text-base font-bold text-slate-900">
                匹配状态暂时无法读取
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                {matchQuery.error instanceof Error
                  ? matchQuery.error.message
                  : "网络连接暂时异常"}
              </p>
            </div>
            <Button size="sm" onClick={() => void matchQuery.refetch()}>
              重试
            </Button>
          </CardContent>
        </Card>
      </AppFrame>
    );
  }

  const current = matchQuery.data ?? null;

  return (
    <AppFrame>
      <div className="max-w-4xl mx-auto space-y-6">
        {/* 1. COMPOSE */}
        {(current === null || current.status === "cancelled") &&
          !justCancelled &&
          !blocked && (
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
                      onChange={(e) =>
                        setWantTag(e.target.value as StrengthTag | "")
                      }
                      className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-800 bg-white"
                    >
                      <option value="" disabled>
                        请选择能力方向
                      </option>
                      {STRENGTH_TAGS.map((tag) => (
                        <option key={tag} value={tag}>
                          {tag}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="p-3 rounded-lg bg-slate-50 border border-slate-100 text-xs text-slate-500 flex flex-col justify-center">
                    <span className="font-semibold text-slate-700">
                      你的提供能力：
                      {myStrengths.length > 0
                        ? myStrengths.join(" · ")
                        : "画像生成中"}
                    </span>
                    <span className="text-slate-400 text-[11px] mt-0.5">
                      来自画像，系统将自动寻找互补伙伴
                    </span>
                  </div>
                </div>

                {submitError && (
                  <p className="text-xs text-rose-600" role="alert">
                    {submitError}
                  </p>
                )}

                <div className="pt-4 border-t border-slate-100 flex justify-end">
                  <Button
                    type="button"
                    disabled={
                      !wantText.trim() ||
                      wantTag === "" ||
                      submitMutation.isPending
                    }
                    onClick={() => submitMutation.mutate()}
                  >
                    {submitMutation.isPending
                      ? "提交中..."
                      : "提交问题进入队列"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

        {/* 2. MATCHED */}
        {current?.status === "matched" && (
          <Card className="bg-white border-slate-200">
            <CardHeader className="pb-3 flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base font-bold text-slate-900">
                双向互补匹配成功
              </CardTitle>
              <Badge
                variant="secondary"
                className="text-emerald-700 bg-emerald-50 border-emerald-200"
              >
                对局就绪
              </Badge>
            </CardHeader>

            <CardContent className="space-y-6">
              <MatchExplanation
                match={current}
                myName={session.user?.name ?? "我"}
                myStrengths={myStrengths}
              />

              <div className="pt-4 border-t border-slate-100 flex items-center justify-end">
                {current.pair_id ? (
                  <Link
                    href={`/exchange?pair_id=${encodeURIComponent(current.pair_id)}`}
                    className={cn(buttonVariants({ size: "sm" }), "gap-1.5")}
                  >
                    <span>进入翻开的叶（对局互答）</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                ) : null}
              </div>
            </CardContent>
          </Card>
        )}

        {/* 3. WAITING */}
        {current?.status === "waiting" && (
          <Card className="bg-white border-slate-200">
            <CardContent className="p-8 text-center space-y-4">
              <RefreshCw className="h-8 w-8 animate-spin text-indigo-600 mx-auto" />
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  “{current.want_text}”
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  正在全网创作者画像中寻找互补伙伴。双方均满足条件时开启对局。
                </p>
                {current.waiting_until ? (
                  <p className="text-xs text-slate-400 mt-1">
                    本需求有效期至 {formatExpiry(current.waiting_until)}
                    ，过期自动作废
                  </p>
                ) : null}
              </div>
              <div className="flex justify-center gap-2 pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={cancelMutation.isPending}
                  onClick={() => cancelMutation.mutate()}
                >
                  {cancelMutation.isPending ? "取消中..." : "取消匹配"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* 4. CANCELLED */}
        {current === null && justCancelled && (
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
              <Button size="sm" onClick={() => setJustCancelled(false)}>
                重新填写
              </Button>
            </CardContent>
          </Card>
        )}

        {/* 5. BLOCKED */}
        {blocked && (
          <Card className="bg-white border-rose-200">
            <CardContent className="p-8 text-center space-y-4">
              <AlertCircle className="h-8 w-8 text-rose-500 mx-auto" />
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  当前不能配对
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  可能是声望低于锁定线，暂时不能进入匹配池。这不是封号。
                </p>
              </div>
              <div className="flex justify-center gap-2">
                <Link
                  href="/settings"
                  className={cn(buttonVariants({ size: "sm" }), "gap-1.5")}
                >
                  去看声望
                </Link>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setBlocked(false)}
                >
                  返回修改
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </AppFrame>
  );
}

export default function MatchPage() {
  return (
    <RequireSession>
      <MatchPageContent />
    </RequireSession>
  );
}
