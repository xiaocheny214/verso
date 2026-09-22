"use client";

import Link from "next/link";
import { Suspense, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  Clock,
  Inbox,
  RefreshCw,
  Send,
  ThumbsDown,
} from "lucide-react";

import { AppFrame } from "@/components/app-frame";
import { useSession } from "@/components/use-session";
import { matchQueryKey, ticketApi } from "@/model/match";
import {
  exchangeListQueryKey,
  exchangeMessageApi,
  exchangeMessagesQueryKey,
  exchangeQueryKey,
  exchangeSessionApi,
} from "@/model/exchange";
import type { Exchange, ExchangeMessage } from "@/model/exchange";
import { qualityApi } from "@/model/quality";
import type { Review, ReviewVerdict } from "@/model/quality";
import { ApiError } from "@/lib/http";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn } from "cn";

const MESSAGE_MAX_LENGTH = 2000;

function formatDateTime(iso: string | null | undefined): string {
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

function formatRemaining(closesAt: string): string {
  const ms = new Date(closesAt).getTime() - Date.now();
  if (Number.isNaN(ms)) return "";
  if (ms <= 0) return "已到期";
  const totalMinutes = Math.floor(ms / 60_000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `剩余 ${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.code === 404;
}

function peerIdOf(exchange: Exchange, myId: string): string | null {
  if (exchange.user_a_id === myId) return exchange.user_b_id;
  if (exchange.user_b_id === myId) return exchange.user_a_id;
  return null;
}

function peerStrengthsLabel(strengths: string[] | undefined): string {
  if (!strengths || strengths.length === 0) return "画像生成中";
  return strengths.join(" · ");
}

const VERDICT_PRESENTATIONS: Record<
  ReviewVerdict,
  { label: string; detail: string; badgeClass: string }
> = {
  poor: {
    label: "判定为差",
    detail: "系统认定回答敷衍，会按规则降低对方声望；分数变动只在后端发生。",
    badgeClass: "text-rose-700 bg-rose-50 border-rose-200",
  },
  good: {
    label: "判定为合格",
    detail: "回答有效，不会影响对方声望。",
    badgeClass: "text-emerald-700 bg-emerald-50 border-emerald-200",
  },
  unclear: {
    label: "暂无法判断",
    detail: "证据不足或复核未成功，不会影响对方声望。",
    badgeClass: "text-amber-700 bg-amber-50 border-amber-200",
  },
};

function ExchangePageContent() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const session = useSession();
  const myId = session.user?.id ?? null;

  const [draft, setDraft] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [reviews, setReviews] = useState<Record<string, Review>>({});
  const [reviewedPairs, setReviewedPairs] = useState<Record<string, true>>({});
  const [reviewError, setReviewError] = useState<string | null>(null);

  const pairsQuery = useQuery({
    queryKey: exchangeListQueryKey,
    queryFn: exchangeSessionApi.exchanges,
    retry: false,
  });

  const pairs = pairsQuery.data ?? [];
  const urlExchangeId = searchParams.get("pair_id");
  const fallbackExchangeId = pairs.length === 1 ? pairs[0].exchange_id : null;
  const exchangeId = urlExchangeId ?? fallbackExchangeId;
  const selectedPair = pairs.find((pair) => pair.exchange_id === exchangeId);

  const exchangeQuery = useQuery({
    queryKey: exchangeQueryKey(exchangeId ?? ""),
    queryFn: () => exchangeSessionApi.exchange(exchangeId as string),
    enabled: exchangeId != null,
    retry: false,
  });

  const messagesQuery = useQuery({
    queryKey: exchangeMessagesQueryKey(exchangeId ?? ""),
    queryFn: () => exchangeMessageApi.messages(exchangeId as string),
    enabled: exchangeId != null,
    retry: false,
  });

  const matchQuery = useQuery({
    queryKey: matchQueryKey,
    queryFn: ticketApi.currentMatch,
    retry: false,
  });

  const exchange = exchangeQuery.data ?? null;
  const isOpen = exchange?.status === "open";
  const peerId = exchange && myId ? peerIdOf(exchange, myId) : null;
  const peerName = selectedPair?.peer_name ?? "对方";
  const peerStrengths = selectedPair?.peer_strengths ?? [];
  const myWantText =
    matchQuery.data?.pair_id != null && matchQuery.data.pair_id === exchangeId
      ? matchQuery.data.want_text
      : null;

  const messages = messagesQuery.data ?? [];
  const peerMessages = messages.filter((m) => m.sender_id === peerId);
  const myMessages = myId ? messages.filter((m) => m.sender_id === myId) : [];

  const exchangeNotFound =
    exchangeQuery.isError && isNotFound(exchangeQuery.error);
  const exchangeErrorTitle = exchangeNotFound
    ? "没有这对关系"
    : "这一对暂时无法读取";
  let exchangeErrorDetail = "网络连接暂时异常";
  if (exchangeNotFound) {
    exchangeErrorDetail =
      "它可能不属于你，或已经不存在。回到列表选择你的对局。";
  } else if (exchangeQuery.error instanceof Error) {
    exchangeErrorDetail = exchangeQuery.error.message;
  }

  const sendMutation = useMutation({
    mutationFn: (text: string) =>
      exchangeMessageApi.sendMessage(exchangeId as string, text),
    onSuccess: (message) => {
      setSendError(null);
      setDraft("");
      queryClient.setQueryData<ExchangeMessage[]>(
        exchangeMessagesQueryKey(exchangeId as string),
        (current) => [...(current ?? []), message],
      );
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 409) {
        setSendError("这对已经结束，不能再留言");
        void queryClient.invalidateQueries({
          queryKey: exchangeQueryKey(exchangeId as string),
        });
        return;
      }
      setSendError(error instanceof Error ? error.message : "发送失败");
    },
  });

  const closeMutation = useMutation({
    mutationFn: () => exchangeSessionApi.closeExchange(exchangeId as string),
    onSuccess: (closed) => {
      queryClient.setQueryData(exchangeQueryKey(exchangeId as string), closed);
    },
  });

  const reviewMutation = useMutation({
    mutationFn: (id: string) => qualityApi.review(id),
    onSuccess: (result) => {
      setReviewError(null);
      setReviews((prev) => ({ ...prev, [result.exchange_id]: result }));
      setReviewedPairs((prev) => ({ ...prev, [result.exchange_id]: true }));
    },
    onError: (error) => {
      if (
        error instanceof ApiError &&
        error.code === 409 &&
        error.message.includes("已经评估过对方")
      ) {
        if (exchangeId != null) {
          setReviewedPairs((prev) => ({ ...prev, [exchangeId]: true }));
        }
        setReviewError(null);
        return;
      }
      setReviewError(
        error instanceof Error && error.message
          ? error.message
          : "质量复核请求失败",
      );
    },
  });

  const review = exchangeId != null ? (reviews[exchangeId] ?? null) : null;
  const alreadyReviewed =
    exchangeId != null && reviewedPairs[exchangeId] === true;

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || exchangeId == null) return;
    sendMutation.mutate(text);
  }

  function openPair(id: string) {
    setReviewError(null);
    router.replace(`/exchange?pair_id=${encodeURIComponent(id)}`);
  }

  function refresh() {
    void exchangeQuery.refetch();
    void messagesQuery.refetch();
  }

  function renderQualityReview() {
    if (review != null) {
      const presentation = VERDICT_PRESENTATIONS[review.verdict];
      return (
        <div className="p-4 pt-3 border-t border-slate-100 space-y-1.5">
          <Badge
            variant="outline"
            className={cn("text-[10px]", presentation.badgeClass)}
          >
            质量复核：{presentation.label}
          </Badge>
          {review.reason && (
            <p className="text-[11px] text-slate-600 leading-relaxed">
              {review.reason}
            </p>
          )}
          <p className="text-[11px] text-slate-400">{presentation.detail}</p>
        </div>
      );
    }

    if (alreadyReviewed) {
      return (
        <div className="p-4 pt-3 border-t border-slate-100">
          <p className="text-[11px] text-slate-500">
            你已评估过对方，这一对不能再评。
          </p>
        </div>
      );
    }

    return (
      <div className="p-4 pt-3 border-t border-slate-100 space-y-2.5">
        <div className="flex items-center justify-between gap-3">
          <p className="text-[11px] text-slate-400 leading-relaxed">
            觉得对方答得敷衍？点「不满意」后，系统才会用你本轮的问题和对方在这对里的全部留言做一次复核；只有判定为差才会影响对方声望。
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="shrink-0 gap-1.5 text-rose-600 hover:text-rose-700"
            disabled={reviewMutation.isPending}
            onClick={() => {
              if (exchangeId != null) reviewMutation.mutate(exchangeId);
            }}
          >
            <ThumbsDown className="h-3 w-3" />
            <span>{reviewMutation.isPending ? "复核中…" : "不满意"}</span>
          </Button>
        </div>
        {reviewError && (
          <p className="text-xs text-rose-600" role="alert">
            {reviewError}
          </p>
        )}
      </div>
    );
  }

  function renderWorkbench() {
    if (exchangeId == null) {
      return (
        <Card className="bg-white border-slate-200">
          <CardContent className="p-8 text-center space-y-2">
            <p className="text-sm font-bold text-slate-900">选择一对互答</p>
            <p className="text-xs text-slate-500">
              从左侧列表选择要查看或继续的对局。
            </p>
          </CardContent>
        </Card>
      );
    }

    if (exchangeQuery.isPending) {
      return (
        <Card className="bg-white border-slate-200">
          <CardContent className="p-8 text-center space-y-3">
            <RefreshCw className="h-7 w-7 animate-spin text-indigo-600 mx-auto" />
            <p className="text-sm text-slate-500">正在打开这一对…</p>
          </CardContent>
        </Card>
      );
    }

    if (exchangeQuery.isError) {
      return (
        <Card className="bg-white border-rose-200">
          <CardContent className="p-8 text-center space-y-4">
            <AlertCircle className="h-8 w-8 text-rose-500 mx-auto" />
            <div>
              <h3 className="text-base font-bold text-slate-900">
                {exchangeErrorTitle}
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                {exchangeErrorDetail}
              </p>
            </div>
            <div className="flex justify-center gap-2">
              {urlExchangeId != null && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => router.replace("/exchange")}
                >
                  查看我的对局
                </Button>
              )}
              <Button size="sm" onClick={refresh}>
                重试
              </Button>
            </div>
          </CardContent>
        </Card>
      );
    }

    if (!exchange) {
      return null;
    }

    return (
      <>
        {/* Session Top Bar */}
        <Card className="bg-white border-slate-200">
          <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-slate-900">
                  与 {peerName} 的互答对局
                </span>
                <Badge
                  variant="secondary"
                  className={
                    isOpen
                      ? "text-emerald-700 bg-emerald-50 border-emerald-200"
                      : "text-slate-600 bg-slate-100"
                  }
                >
                  {isOpen ? "24h 互答中" : "已归档"}
                </Badge>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 text-xs text-slate-500">
                <Clock className="h-3.5 w-3.5 text-indigo-600" />
                <span className="font-semibold">
                  {isOpen
                    ? formatRemaining(exchange.closes_at)
                    : `结束于 ${formatDateTime(exchange.closed_at ?? exchange.closes_at)}`}
                </span>
              </div>

              <div className="flex items-center gap-1 pl-3 border-l border-slate-200">
                <Button
                  type="button"
                  variant="outline"
                  size="xs"
                  disabled={messagesQuery.isFetching}
                  onClick={refresh}
                >
                  <RefreshCw
                    className={cn(
                      "h-3 w-3",
                      messagesQuery.isFetching && "animate-spin",
                    )}
                  />
                  <span>刷新留言</span>
                </Button>
                {isOpen && (
                  <Button
                    type="button"
                    variant="outline"
                    size="xs"
                    disabled={closeMutation.isPending}
                    onClick={() => closeMutation.mutate()}
                  >
                    {closeMutation.isPending ? "关闭中…" : "提前结束"}
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Dual Lanes */}
        <div className="grid md:grid-cols-2 gap-6 items-start">
          {/* Peer's Answer to Me */}
          <Card className="bg-white border-slate-200 flex flex-col min-h-[440px]">
            <CardHeader className="pb-3 border-b border-slate-100 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-800">
                  {peerName} 正在回答你的问题
                </span>
                {peerStrengths.length > 0 && (
                  <Badge
                    variant="outline"
                    className="text-emerald-700 bg-emerald-50 border-emerald-200 text-[10px]"
                  >
                    {peerStrengths[0]}
                  </Badge>
                )}
              </div>
              <div className="text-xs text-slate-900 font-semibold bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                {myWantText ??
                  "本轮匹配窗口已结束，你的问题原文暂不可见，仍可回看下方留言。"}
              </div>
            </CardHeader>

            <CardContent className="py-4 space-y-3 flex-1 overflow-y-auto">
              {peerMessages.map((m) => (
                <div
                  key={m.id}
                  className="p-3.5 rounded-lg bg-emerald-50/60 border border-emerald-100 text-xs text-slate-800 leading-relaxed space-y-1.5"
                >
                  <p>{m.text}</p>
                  <div className="text-[10px] text-emerald-700 font-medium">
                    {peerName} · {formatDateTime(m.created_at)}
                  </div>
                </div>
              ))}

              {peerMessages.length === 0 && (
                <div className="py-12 text-center text-xs text-slate-400">
                  {messagesQuery.isFetching
                    ? "正在拉取留言…"
                    : "对方还未留言。稍后回来刷新即可看到。"}
                </div>
              )}
            </CardContent>

            {peerMessages.length > 0 && renderQualityReview()}
          </Card>

          {/* My Answer to Peer */}
          <Card className="bg-white border-slate-200 flex flex-col min-h-[440px]">
            <CardHeader className="pb-3 border-b border-slate-100 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-800">
                  你正在回答 {peerName} 的问题
                </span>
              </div>
              <div className="text-xs text-slate-900 font-semibold bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                {selectedPair?.peer_want_text ?? "对方的问题暂不可见。"}
              </div>
            </CardHeader>

            <CardContent className="py-4 space-y-3 flex-1 overflow-y-auto">
              {myMessages.map((m) => (
                <div
                  key={m.id}
                  className="p-3.5 rounded-lg bg-indigo-50/60 border border-indigo-100 text-xs text-slate-800 leading-relaxed space-y-1.5"
                >
                  <p>{m.text}</p>
                  <div className="text-[10px] text-indigo-700 font-medium">
                    你 · {formatDateTime(m.created_at)}
                  </div>
                </div>
              ))}

              {myMessages.length === 0 && (
                <div className="py-12 text-center text-xs text-slate-400">
                  留下你的第一条针对性建议。
                </div>
              )}
            </CardContent>

            {isOpen ? (
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
                  maxLength={MESSAGE_MAX_LENGTH}
                  rows={3}
                  className="resize-none text-xs"
                />
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-slate-400">
                    {draft.length} / {MESSAGE_MAX_LENGTH} 字
                  </span>
                  <Button
                    type="submit"
                    size="sm"
                    disabled={!draft.trim() || sendMutation.isPending}
                    className="gap-1.5"
                  >
                    <Send className="h-3 w-3" />
                    <span>
                      {sendMutation.isPending ? "发送中…" : "发送回答"}
                    </span>
                  </Button>
                </div>
                {sendError && (
                  <p className="text-xs text-rose-600" role="alert">
                    {sendError}
                  </p>
                )}
              </form>
            ) : (
              <div className="p-4 pt-3 border-t border-slate-100 text-center space-y-1 text-xs">
                <span className="font-bold text-slate-600 block">
                  本轮对局已归档
                </span>
                <p className="text-slate-400 text-[11px]">
                  {sendError ?? "答案已保留。若需新的解答，请发起新匹配。"}
                </p>
              </div>
            )}
          </Card>
        </div>
      </>
    );
  }

  if (pairsQuery.isPending) {
    return (
      <AppFrame>
        <Card className="bg-white border-slate-200">
          <CardContent className="p-8 text-center space-y-3">
            <RefreshCw className="h-7 w-7 animate-spin text-indigo-600 mx-auto" />
            <p className="text-sm text-slate-500">正在读取互答对局…</p>
          </CardContent>
        </Card>
      </AppFrame>
    );
  }

  if (pairsQuery.isError) {
    return (
      <AppFrame>
        <Card className="bg-white border-rose-200">
          <CardContent className="p-8 text-center space-y-4">
            <AlertCircle className="h-8 w-8 text-rose-500 mx-auto" />
            <div>
              <h3 className="text-base font-bold text-slate-900">
                互答对局暂时无法读取
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                {pairsQuery.error instanceof Error
                  ? pairsQuery.error.message
                  : "网络连接暂时异常"}
              </p>
            </div>
            <Button size="sm" onClick={() => void pairsQuery.refetch()}>
              重试
            </Button>
          </CardContent>
        </Card>
      </AppFrame>
    );
  }

  if (pairs.length === 0) {
    return (
      <AppFrame>
        <Card className="bg-white border-slate-200">
          <CardContent className="p-10 text-center space-y-4">
            <Inbox className="h-9 w-9 text-slate-300 mx-auto" />
            <div>
              <h3 className="text-base font-bold text-slate-900">
                还没有互答对局
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                发起一次互补匹配，配上后系统会自动开启 24 小时互答窗口。
              </p>
            </div>
            <Link
              href="/match"
              className={cn(buttonVariants({ size: "sm" }), "gap-1.5")}
            >
              <span>去发起匹配</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </CardContent>
        </Card>
      </AppFrame>
    );
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
                对局列表 ({pairs.length})
              </span>
            </div>

            {pairs.map((pair) => {
              const active = pair.exchange_id === exchangeId;
              return (
                <Card
                  key={pair.exchange_id}
                  className={cn(
                    "bg-white shadow-xs cursor-pointer transition-colors",
                    active
                      ? "border-2 border-indigo-600"
                      : "border-slate-200 hover:border-indigo-200",
                  )}
                  onClick={() => openPair(pair.exchange_id)}
                >
                  <CardContent className="p-4 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Avatar size="sm">
                          {pair.peer_avatar_url ? (
                            <AvatarImage
                              src={pair.peer_avatar_url}
                              alt={pair.peer_name}
                            />
                          ) : null}
                          <AvatarFallback>
                            {pair.peer_name.slice(0, 1)}
                          </AvatarFallback>
                        </Avatar>
                        <div>
                          <span className="text-xs font-bold text-slate-900 block">
                            {pair.peer_name}
                          </span>
                          <span className="text-[10px] text-slate-400 block">
                            {peerStrengthsLabel(pair.peer_strengths)}
                          </span>
                        </div>
                      </div>
                      {active && (
                        <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                      )}
                    </div>

                    <div className="text-[11px] text-slate-600 line-clamp-2 bg-slate-50 p-2 rounded">
                      求教：{pair.peer_want_text}
                    </div>

                    <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-100">
                      <span>{pair.exchange_id.slice(0, 8)}</span>
                      {active && (
                        <span className="text-indigo-600 font-semibold">
                          当前对局
                        </span>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </aside>

          {/* Right: MAIN WORKBENCH */}
          <div className="lg:col-span-3 space-y-6">{renderWorkbench()}</div>
        </div>
      </div>
    </AppFrame>
  );
}

export default function ExchangePage() {
  return (
    <Suspense fallback={null}>
      <ExchangePageContent />
    </Suspense>
  );
}
