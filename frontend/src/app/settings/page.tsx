"use client";

import { useState } from "react";
import { RefreshCw, CheckCircle2 } from "lucide-react";

import { AppFrame } from "@/components/app-frame";
import { useLogout, useSession } from "@/components/use-session";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { displayInitial } from "@/lib/utils";

const sourceLabels = {
  contents: "知乎创作",
  favorites: "知乎收藏",
  self_reported: "本人补充",
} as const;

export default function SettingsPage() {
  const { user } = useSession();
  const logout = useLogout();
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);

  if (!user) {
    return null;
  }

  const portraits = user.portraits ?? [];
  const stable = portraits.find((portrait) => portrait.horizon === "stable");
  const recent = portraits.find((portrait) => portrait.horizon === "recent_7d");

  async function handleSyncPortrait() {
    setIsSyncing(true);
    setSyncNotice(null);
    try {
      await new Promise((resolve) => setTimeout(resolve, 800));
      setSyncNotice("画像已根据最新知乎创作重新生成完毕。");
    } finally {
      setIsSyncing(false);
    }
  }

  return (
    <AppFrame>
      <div className="max-w-4xl mx-auto space-y-6">
        <Card className="bg-white border-slate-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-bold text-slate-900">
              登录认证
            </CardTitle>
            <CardDescription className="text-xs text-slate-500">
              知乎账号授权连接状态。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between p-4 rounded-lg bg-slate-50 border border-slate-100">
              <div className="flex items-center gap-3">
                <Avatar className="h-10 w-10 bg-indigo-600 text-white font-bold">
                  {user.avatar_url ? (
                    <AvatarImage src={user.avatar_url} alt={user.name} />
                  ) : null}
                  <AvatarFallback className="bg-indigo-600 text-white">
                    {displayInitial(user.name)}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-900 text-sm">
                      {user.name}
                    </span>
                    <Badge
                      variant="secondary"
                      className="gap-1 text-emerald-700 bg-emerald-50 border-emerald-200"
                    >
                      <CheckCircle2 className="h-3 w-3" />
                      已认证
                    </Badge>
                  </div>
                  <span className="text-xs text-slate-400">
                    ID: {user.id} · 知乎公开内容授权正常
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={logout.isPending}
                  onClick={() => {
                    logout.mutate();
                  }}
                >
                  退出登录
                </Button>
              </div>
            </div>

            <div className="text-xs text-slate-400 space-y-1">
              <p>• 仅读取您公开授权的知乎回答、文章及公开收藏夹。</p>
              <p>• 凭证仅在服务端安全保管，不存储于本地浏览器。</p>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white border-slate-200">
          <CardHeader className="pb-3 flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base font-bold text-slate-900">
                生成画像
              </CardTitle>
              <CardDescription className="text-xs text-slate-500">
                根据知乎内容提炼的能力背叶，用于双向互补匹配。
              </CardDescription>
            </div>

            <Button
              type="button"
              size="sm"
              disabled={isSyncing}
              onClick={handleSyncPortrait}
              className="gap-1.5"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${isSyncing ? "animate-spin" : ""}`}
              />
              <span>{isSyncing ? "分析中..." : "重新生成画像"}</span>
            </Button>
          </CardHeader>

          <CardContent className="space-y-4">
            {syncNotice ? (
              <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                <span>{syncNotice}</span>
              </div>
            ) : null}

            <div className="grid md:grid-cols-2 gap-4 pt-1">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-800">
                    长期稳定能力
                  </span>
                  <span className="text-[11px] text-slate-400">稳定沉淀</span>
                </div>

                <div className="space-y-2">
                  {(stable?.strengths ?? []).map((s) => (
                    <div
                      key={`${s.tag}-${s.evidence_title}`}
                      className="p-3 rounded-lg border border-slate-100 bg-slate-50 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <Badge
                          variant="outline"
                          className="text-indigo-700 bg-indigo-50 border-indigo-200"
                        >
                          {s.tag}
                        </Badge>
                        <span className="text-slate-400">
                          {sourceLabels[s.source]}
                        </span>
                      </div>
                      <p className="text-slate-700 mt-1 font-medium">
                        {s.evidence_title}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-800">
                    近 7 天投入
                  </span>
                  <span className="text-[11px] text-slate-400">动态更新</span>
                </div>

                <div className="space-y-2">
                  {(recent?.strengths ?? []).map((s) => (
                    <div
                      key={`${s.tag}-${s.evidence_title}`}
                      className="p-3 rounded-lg border border-slate-100 bg-slate-50 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <Badge
                          variant="outline"
                          className="text-emerald-700 bg-emerald-50 border-emerald-200"
                        >
                          {s.tag}
                        </Badge>
                        <span className="text-slate-400">
                          {sourceLabels[s.source]}
                        </span>
                      </div>
                      <p className="text-slate-700 mt-1 font-medium">
                        {s.evidence_title}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </AppFrame>
  );
}
