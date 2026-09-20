"use client";

import { useState } from "react";
import { AlertCircle, CheckCircle2, RefreshCw } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { sessionQueryKey } from "@/model/auth";
import { articlesQueryKey } from "@/model/article";
import {
  STRENGTH_TAGS,
  isPortraitConflict,
  isPortraitGrantExpired,
  portraitApi,
  type Strength,
  type StrengthTag,
  type UserCard,
} from "@/model/portrait";
import { useZhihuLogin } from "@/components/use-session";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const sourceLabels = {
  contents: "知乎创作",
  favorites: "知乎收藏",
  self_reported: "本人补充",
} as const;

type Notice = {
  kind: "success" | "error";
  text: string;
};

function canSelfReport(strengths: Strength[]): boolean {
  return strengths.every((item) => item.source === "self_reported");
}

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function EvidenceTitle({ title, url }: { title: string; url?: string | null }) {
  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="block text-slate-700 mt-1 font-medium hover:underline"
      >
        {title}
      </a>
    );
  }

  return <p className="text-slate-700 mt-1 font-medium">{title}</p>;
}

function StrengthList({
  strengths,
  emptyText,
  badgeClassName,
}: {
  strengths: Strength[];
  emptyText: string;
  badgeClassName: string;
}) {
  if (strengths.length === 0) {
    return <p className="text-xs text-slate-400">{emptyText}</p>;
  }

  return (
    <div className="space-y-2">
      {strengths.map((item) => (
        <div
          key={`${item.tag}-${item.source}-${item.evidence_url ?? item.evidence_title ?? ""}`}
          className="p-3 rounded-lg border border-slate-100 bg-slate-50 text-xs"
        >
          <div className="flex items-center justify-between">
            <Badge variant="outline" className={badgeClassName}>
              {item.tag}
            </Badge>
            <span className="text-slate-400">{sourceLabels[item.source]}</span>
          </div>
          {item.evidence_title ? (
            <EvidenceTitle
              title={item.evidence_title}
              url={item.evidence_url}
            />
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function PortraitPanel({ user }: { user: UserCard }) {
  const queryClient = useQueryClient();
  const login = useZhihuLogin();
  const [notice, setNotice] = useState<Notice | null>(null);
  const [needsRelogin, setNeedsRelogin] = useState(false);
  const [selectedTags, setSelectedTags] = useState<StrengthTag[]>(() =>
    (
      (user.portraits ?? []).find((portrait) => portrait.horizon === "stable")
        ?.strengths ?? []
    )
      .filter((item) => item.source === "self_reported")
      .map((item) => item.tag),
  );

  const portraits = user.portraits ?? [];
  const stable = portraits.find((portrait) => portrait.horizon === "stable");
  const recent = portraits.find((portrait) => portrait.horizon === "recent_7d");
  const stableStrengths = stable?.strengths ?? [];
  const recentStrengths = recent?.strengths ?? [];
  const allowSelfReport = canSelfReport(stableStrengths);
  const emptyPortrait =
    stableStrengths.length === 0 && recentStrengths.length === 0;

  const sync = useMutation({
    mutationFn: portraitApi.syncPortrait,
    onSuccess: (card: UserCard) => {
      queryClient.setQueryData(sessionQueryKey, card);
      void queryClient.invalidateQueries({ queryKey: articlesQueryKey });
      setNeedsRelogin(false);
      setNotice({
        kind: "success",
        text: "画像已根据最新知乎授权数据更新。",
      });
    },
    onError: (error: Error) => {
      if (isPortraitGrantExpired(error)) {
        setNeedsRelogin(true);
        setNotice({
          kind: "error",
          text: messageOf(error, "授权已过期，请重新登录"),
        });
        return;
      }
      setNotice({
        kind: "error",
        text: messageOf(error, "画像同步失败，请稍后重试"),
      });
    },
  });

  const selfReport = useMutation({
    mutationFn: portraitApi.selfReport,
    onSuccess: (card: UserCard) => {
      queryClient.setQueryData(sessionQueryKey, card);
      setNotice({
        kind: "success",
        text: "已保存本人补充的稳定画像。",
      });
    },
    onError: (error: Error) => {
      if (isPortraitConflict(error)) {
        setNotice({
          kind: "error",
          text: messageOf(error, "已有知乎画像，不能自报覆盖"),
        });
        return;
      }
      if (isPortraitGrantExpired(error)) {
        setNeedsRelogin(true);
        setNotice({
          kind: "error",
          text: messageOf(error, "授权已过期，请重新登录"),
        });
        return;
      }
      setNotice({
        kind: "error",
        text: messageOf(error, "自报失败，请稍后重试"),
      });
    },
  });

  const busy = sync.isPending || selfReport.isPending;

  function toggleTag(tag: StrengthTag) {
    setSelectedTags((current: StrengthTag[]) => {
      if (current.includes(tag)) {
        return current.filter((item: StrengthTag) => item !== tag);
      }
      if (current.length >= 3) {
        return current;
      }
      return [...current, tag];
    });
  }

  return (
    <Card className="bg-white border-slate-200">
      <CardHeader className="pb-3 flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="text-base font-bold text-slate-900">
            擅长画像
          </CardTitle>
          <CardDescription className="text-xs text-slate-500">
            根据知乎授权内容抽取。抽不出时才可以本人补充 1–3 个标签。
          </CardDescription>
        </div>

        <Button
          type="button"
          size="sm"
          disabled={busy}
          onClick={() => {
            setNotice(null);
            sync.mutate();
          }}
          className="gap-1.5"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${sync.isPending ? "animate-spin" : ""}`}
          />
          <span>{sync.isPending ? "同步中..." : "重新同步知乎"}</span>
        </Button>
      </CardHeader>

      <CardContent className="space-y-4">
        {notice ? (
          <div
            className={
              notice.kind === "success"
                ? "p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2"
                : "p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2"
            }
          >
            {notice.kind === "success" ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
            ) : (
              <AlertCircle className="h-4 w-4 text-rose-600 shrink-0" />
            )}
            <span>{notice.text}</span>
          </div>
        ) : null}

        {needsRelogin ? (
          <div className="flex items-center justify-between gap-3 p-3 rounded-lg border border-amber-200 bg-amber-50">
            <p className="text-xs text-amber-800">
              知乎授权已过期。请重新登录，前端不会改写或保存知乎凭证。
            </p>
            <Button
              type="button"
              size="sm"
              disabled={login.isPending}
              onClick={() => {
                login.mutate();
              }}
            >
              {login.isPending ? "正在跳转知乎…" : "重新登录"}
            </Button>
          </div>
        ) : null}

        {emptyPortrait ? (
          <p className="text-xs text-slate-500">
            还没有抽出擅长。登录时同步失败不会挡住登录，可以再同步一次，或在抽不出时自行补充。
          </p>
        ) : null}

        <div className="grid md:grid-cols-2 gap-4 pt-1">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-800">
                长期稳定能力
              </span>
              <span className="text-[11px] text-slate-400">稳定沉淀</span>
            </div>
            <StrengthList
              strengths={stableStrengths}
              emptyText="还没有长期擅长。"
              badgeClassName="text-indigo-700 bg-indigo-50 border-indigo-200"
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-800">
                近 7 天投入
              </span>
              <span className="text-[11px] text-slate-400">动态更新</span>
            </div>
            <StrengthList
              strengths={recentStrengths}
              emptyText="近 7 天还没有抽出擅长。"
              badgeClassName="text-emerald-700 bg-emerald-50 border-emerald-200"
            />
          </div>
        </div>

        {allowSelfReport ? (
          <div className="space-y-3 pt-2 border-t border-slate-100">
            <div>
              <p className="text-xs font-bold text-slate-800">本人补充擅长</p>
              <p className="text-[11px] text-slate-400 mt-0.5">
                仅在没有知乎创作或收藏抽出的稳定画像时可用，最多 3 个。
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {STRENGTH_TAGS.map((tag) => {
                const selected = selectedTags.includes(tag);
                return (
                  <Button
                    key={tag}
                    type="button"
                    size="sm"
                    variant={selected ? "default" : "outline"}
                    aria-pressed={selected}
                    disabled={busy || (!selected && selectedTags.length >= 3)}
                    onClick={() => {
                      toggleTag(tag);
                    }}
                    className="h-7 text-xs px-2.5"
                  >
                    {tag}
                  </Button>
                );
              })}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-slate-400">
                已选 {selectedTags.length} / 3
              </span>
              <Button
                type="button"
                size="sm"
                disabled={busy || selectedTags.length < 1}
                onClick={() => {
                  setNotice(null);
                  selfReport.mutate(selectedTags);
                }}
              >
                {selfReport.isPending ? "保存中..." : "保存补充"}
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-xs text-slate-400 pt-2 border-t border-slate-100">
            已有知乎创作或收藏抽出的稳定画像，不能再用自报覆盖。
          </p>
        )}
      </CardContent>
    </Card>
  );
}
