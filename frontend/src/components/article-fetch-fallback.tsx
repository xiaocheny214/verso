"use client";

import { useState } from "react";
import { AlertCircle, BookmarkPlus, ExternalLink } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import {
  articleApi,
  articlesQueryKey,
  isArticleGrantExpired,
} from "@/model/article";
import { captureBookmarklet } from "@/lib/zhihu-capture";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function ArticleFetchFallback() {
  const [zhihuReady, setZhihuReady] = useState(false);
  const failedQuery = useQuery({
    queryKey: articlesQueryKey,
    queryFn: articleApi.failedFetch,
    retry: false,
  });

  const items = failedQuery.data?.items ?? [];
  const token = failedQuery.data?.capture_token ?? "";
  if (failedQuery.isPending || failedQuery.isError) {
    if (failedQuery.isError && isArticleGrantExpired(failedQuery.error)) {
      return null;
    }
    return null;
  }
  if (items.length === 0) {
    return null;
  }

  const bookmarklet = token ? captureBookmarklet(token) : "";

  function openFailedArticle(url: string) {
    window.open(url, "_blank", "noopener,noreferrer");
  }

  return (
    <Card className="bg-white border-amber-200">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-bold text-slate-900">
          有 {items.length} 篇要在你的浏览器里补抓
        </CardTitle>
        <CardDescription className="text-xs text-slate-500">
          提取脚本是前端的，但必须跑在知乎页面上。Verso
          检测不到知乎登录，也不能在跳转后继续执行本站代码。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ol className="space-y-3 text-xs text-slate-700">
          <li className="rounded-lg border border-slate-100 bg-slate-50 p-3 space-y-2">
            <p className="font-bold text-slate-800">1. 确认已在本机登录知乎</p>
            <p className="text-slate-500">
              浏览器不会把知乎 Cookie 给
              Verso。请先打开知乎确认是登录态，再回来点下面按钮。
            </p>
            <Button
              type="button"
              size="sm"
              variant={zhihuReady ? "default" : "outline"}
              onClick={() => {
                setZhihuReady(true);
                window.open(
                  "https://www.zhihu.com/",
                  "_blank",
                  "noopener,noreferrer",
                );
              }}
            >
              {zhihuReady ? "已确认，继续" : "打开知乎，我去登录"}
            </Button>
          </li>
          <li className="rounded-lg border border-slate-100 bg-slate-50 p-3 space-y-2">
            <p className="font-bold text-slate-800">2. 跳到抓取失败的原文</p>
            <p className="text-slate-500">
              由前端打开链接。新标签是知乎站，提取要在那边做。
            </p>
            <ul className="space-y-2">
              {items.map((item) => (
                <li key={item.id}>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={!zhihuReady}
                    className="w-full justify-between h-auto py-2 px-3 font-normal"
                    onClick={() => {
                      openFailedArticle(item.source_url);
                    }}
                  >
                    <span className="truncate text-left">
                      {item.title || item.source_url}
                    </span>
                    <ExternalLink className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                  </Button>
                </li>
              ))}
            </ul>
          </li>
          <li className="rounded-lg border border-slate-100 bg-slate-50 p-3 space-y-2">
            <p className="font-bold text-slate-800">
              3. 在知乎页提取 HTML 并发送给后端
            </p>
            <p className="text-slate-500">
              把下面这颗按钮拖到书签栏。切到第 2
              步打开的知乎文章，点该书签：脚本取正文，POST 到
              /me/articles/browser-capture。
            </p>
            {bookmarklet ? (
              <a
                href={bookmarklet}
                onClick={(event) => {
                  event.preventDefault();
                }}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-slate-200 bg-white text-xs font-medium text-slate-800"
              >
                <BookmarkPlus className="h-3.5 w-3.5" />
                存到 Verso（拖到书签栏，在知乎页点）
              </a>
            ) : null}
          </li>
        </ol>
        <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start gap-2">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>
            在 Verso 设置页点「存到
            Verso」不会提取任何正文。必须在已经打开的知乎文章标签上点书签。
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
