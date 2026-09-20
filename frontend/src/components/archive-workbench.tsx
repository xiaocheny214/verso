"use client";

import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  BookmarkPlus,
  ExternalLink,
  RefreshCw,
  ShieldCheck,
  SquareArrowOutUpRight,
} from "lucide-react";

import {
  articleApi,
  articleQueueQueryKey,
  isArticleGrantExpired,
  type ArticleArchive,
} from "@/model/article";
import {
  captureBookmarklet,
  ZHIHU_HOME_URL,
  ZHIHU_WINDOW_NAME,
} from "@/lib/zhihu-capture";
import { Button } from "@/components/ui/button";

const QUEUE_POLL_MS = 3000;

function kindLabel(url: string): string {
  return url.includes("zhuanlan") || /\/p\/\d+/.test(url) ? "专栏" : "回答";
}

function statusLabel(status: string): string {
  if (status === "failed") return "回传失败";
  if (status === "pending") return "待抓";
  return status;
}

function isWindowAlive(handle: Window | null): boolean {
  return Boolean(handle && !handle.closed);
}

export function ArchiveWorkbench() {
  const zhihuWindow = useRef<Window | null>(null);
  const [windowOpen, setWindowOpen] = useState(false);
  const [currentUrl, setCurrentUrl] = useState("");
  const [notice, setNotice] = useState("");

  const queueQuery = useQuery({
    queryKey: articleQueueQueryKey,
    queryFn: articleApi.queue,
    retry: false,
    refetchInterval: (query) =>
      (query.state.data?.items?.length ?? 0) > 0 ? QUEUE_POLL_MS : false,
  });

  const items = useMemo(
    () => queueQuery.data?.items ?? [],
    [queueQuery.data?.items],
  );
  const token = queueQuery.data?.capture_token ?? "";
  const pendingCount = queueQuery.data?.pending_count ?? 0;
  const failedCount = queueQuery.data?.failed_count ?? 0;
  const readyCount = queueQuery.data?.ready_count ?? 0;
  const bookmarklet = token ? captureBookmarklet(token) : "";

  let queueDetail = "还没有归档条目。请先在设置里同步画像。";
  if (items.length > 0) {
    queueDetail = `还有 ${items.length} 篇要在知乎窗里补抓。`;
  } else if (readyCount > 0) {
    queueDetail = "没有待抓条目。同步画像后，新的专栏和回答会出现在这里。";
  }

  let tokenDetail = "队列为空时不需要凭证。";
  if (token) {
    tokenDetail = "书签里的短时凭证已就绪，请在十分钟内完成提取。";
  } else if (items.length) {
    tokenDetail = "没有拿到回传凭证，请刷新工作台。";
  }

  function rememberWindow(handle: Window | null) {
    zhihuWindow.current = handle;
    setWindowOpen(isWindowAlive(handle));
  }

  function openInZhihuWindow(url: string) {
    const handle = window.open(url, ZHIHU_WINDOW_NAME);
    rememberWindow(handle);
    setCurrentUrl(url);
    if (!handle) {
      setNotice("浏览器拦住了弹窗。请允许本页打开新窗口后再试。");
      return;
    }
    handle.focus();
  }

  const checks = useMemo(
    () => [
      {
        id: "session",
        ok: !queueQuery.isError || !isArticleGrantExpired(queueQuery.error),
        title: "Verso 登录",
        detail: queueQuery.isError
          ? "会话失效，请回到首页重新用知乎登录。"
          : "当前页面已登录 Verso。",
      },
      {
        id: "queue",
        ok: items.length > 0,
        title: "待抓队列",
        detail: queueDetail,
      },
      {
        id: "token",
        ok: items.length === 0 || Boolean(token),
        title: "回传凭证",
        detail: tokenDetail,
      },
      {
        id: "window",
        ok: windowOpen,
        title: "知乎窗口",
        detail: windowOpen
          ? "已打开命名窗口 verso-zhihu。登录态只留在这个窗口里。"
          : "还没打开知乎窗口。点下面「打开知乎窗口」，在新窗口里确认已登录。",
      },
    ],
    [
      items.length,
      queueDetail,
      queueQuery.error,
      queueQuery.isError,
      token,
      tokenDetail,
      windowOpen,
    ],
  );
  const failedChecks = checks.filter((check) => !check.ok);

  if (queueQuery.isPending) {
    return <p className="text-sm text-slate-500">正在读取归档队列…</p>;
  }

  if (queueQuery.isError && isArticleGrantExpired(queueQuery.error)) {
    return (
      <p className="text-sm text-rose-600">
        登录已过期，请回到首页重新用知乎登录。
      </p>
    );
  }

  if (queueQuery.isError) {
    return (
      <p className="text-sm text-rose-600">
        {queueQuery.error instanceof Error
          ? queueQuery.error.message
          : "归档队列暂时无法读取"}
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-[11px] font-semibold tracking-[0.16em] text-indigo-600">
              ARCHIVE WORKBENCH
            </div>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
              创作归档
            </h1>
            <p className="mt-1 text-xs text-slate-500">
              在你自己的 Chrome
              里打开知乎窗口，工作台只负责推链接和收正文。Verso 不读取知乎
              Cookie。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                void queueQuery.refetch();
              }}
              disabled={queueQuery.isFetching}
            >
              <RefreshCw
                className={`mr-1.5 h-3.5 w-3.5 ${queueQuery.isFetching ? "animate-spin" : ""}`}
              />
              刷新
            </Button>
            <span className="rounded-full bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700">
              {windowOpen ? "知乎窗已打开" : "知乎窗未打开"}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => {
              openInZhihuWindow(ZHIHU_HOME_URL);
              setNotice("请在新窗口确认已登录知乎，再回来打开待抓篇目。");
            }}
            className={`min-h-[112px] rounded-2xl p-4 text-left transition ${
              windowOpen
                ? "border-2 border-indigo-600 bg-indigo-600 text-white shadow-lg shadow-indigo-200"
                : "border border-slate-200 bg-slate-50 text-slate-900 hover:border-indigo-300"
            }`}
          >
            <div className="mb-2 flex items-center justify-between">
              <span className="text-base font-bold">打开知乎窗口</span>
              <SquareArrowOutUpRight className="h-4 w-4" />
            </div>
            <p
              className={`text-xs leading-5 ${windowOpen ? "text-white/80" : "text-slate-500"}`}
            >
              只开一次。之后点队列里的篇目，会在同一扇窗里跳转。
            </p>
          </button>
          <button
            type="button"
            disabled={!items[0]}
            onClick={() => {
              if (!items[0]) return;
              openInZhihuWindow(items[0].source_url);
              setNotice("已在知乎窗打开当前篇。切到那个标签，点书签提取正文。");
            }}
            className="min-h-[112px] rounded-2xl border border-slate-200 bg-slate-50 p-4 text-left transition hover:border-indigo-300 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <div className="mb-2 flex items-center justify-between">
              <span className="text-base font-bold text-slate-900">
                开始补抓队列
              </span>
              <ExternalLink className="h-4 w-4 text-slate-400" />
            </div>
            <p className="text-xs leading-5 text-slate-500">
              {items[0]
                ? `下一篇：${items[0].title || items[0].source_url}`
                : "当前没有待抓篇目。"}
            </p>
          </button>
        </div>

        {notice ? (
          <div className="mt-3 rounded-xl bg-indigo-50 px-4 py-3 text-sm text-indigo-800">
            {notice}
          </div>
        ) : null}

        {failedChecks.length > 0 ? (
          <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-900">
              <ShieldCheck className="h-4 w-4 text-amber-700" />
              启动检查有 {failedChecks.length} 项提醒
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {failedChecks.map((check) => (
                <div
                  key={check.id}
                  className="rounded-xl border border-amber-200 bg-white px-3 py-3"
                >
                  <div className="text-xs font-semibold text-slate-500">
                    {check.title}
                  </div>
                  <p className="mt-1 text-xs leading-5 text-slate-600">
                    {check.detail}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      <section className="grid grid-cols-3 gap-3">
        {[
          { label: "待抓", value: pendingCount },
          { label: "失败", value: failedCount, highlight: failedCount > 0 },
          { label: "已就绪", value: readyCount },
        ].map((item) => (
          <div
            key={item.label}
            className="rounded-2xl border border-slate-200 bg-white p-4"
          >
            <div className="text-xs text-slate-500">{item.label}</div>
            <div
              className={`mt-1 text-2xl font-bold ${
                item.highlight ? "text-rose-600" : "text-slate-900"
              }`}
            >
              {item.value}
            </div>
          </div>
        ))}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-slate-900">待抓队列</h2>
            <p className="mt-1 text-xs text-slate-500">
              在知乎窗打开后，切到那个标签，用书签把正文发回 Verso。
            </p>
          </div>
          {bookmarklet ? (
            <a
              href={bookmarklet}
              onClick={(event) => {
                event.preventDefault();
              }}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-800"
            >
              <BookmarkPlus className="h-3.5 w-3.5" />
              存到 Verso（拖到书签栏）
            </a>
          ) : null}
        </div>
        {items.length ? (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {items.map((item) => (
              <QueueCard
                key={item.id}
                item={item}
                active={item.source_url === currentUrl}
                disabled={!windowOpen}
                onOpen={() => {
                  openInZhihuWindow(item.source_url);
                  setNotice("已在知乎窗打开这一篇。切过去后点书签。");
                }}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-5 text-sm text-slate-500">
            当前没有待抓篇目。
          </div>
        )}
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            在本页点「存到
            Verso」不会提取正文。必须拖到书签栏，在已经打开的知乎文章标签上再点。
          </span>
        </div>
      </section>
    </div>
  );
}

function QueueCard({
  item,
  active,
  disabled,
  onOpen,
}: {
  item: ArticleArchive;
  active: boolean;
  disabled: boolean;
  onOpen: () => void;
}) {
  return (
    <div
      className={`rounded-2xl border p-4 ${
        active
          ? "border-indigo-300 bg-indigo-50"
          : "border-slate-200 bg-slate-50"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-bold text-slate-900">
            {item.title || item.source_url}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            {kindLabel(item.source_url)} · {statusLabel(item.status)}
            {item.error_class ? ` · ${item.error_class}` : ""}
          </div>
        </div>
      </div>
      <div className="mt-3">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={disabled}
          onClick={onOpen}
        >
          <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
          在知乎窗打开
        </Button>
      </div>
    </div>
  );
}
