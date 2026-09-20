"use client";

import Link from "next/link";
import { CheckCircle2, ArrowRight } from "lucide-react";

import { useQuery } from "@tanstack/react-query";

import { AppFrame } from "@/components/app-frame";
import { PortraitPanel } from "@/components/portrait-panel";
import { ReputationMeter } from "@/components/reputation-meter";
import { useLogout, useSession } from "@/components/use-session";
import { reputationApi, reputationQueryKey } from "@/model/reputation";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { displayInitial, cn } from "@/lib/utils";

export default function SettingsPage() {
  const { user } = useSession();
  const logout = useLogout();
  const reputationQuery = useQuery({
    queryKey: reputationQueryKey,
    queryFn: reputationApi.me,
    retry: false,
  });

  if (!user) {
    return null;
  }

  const reputationError =
    reputationQuery.error instanceof Error
      ? reputationQuery.error.message
      : "声望暂时无法读取";

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
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-bold text-slate-900">
              声望
            </CardTitle>
            <CardDescription className="text-xs text-slate-500">
              只读资格，决定你能不能进入匹配。不是封号。
            </CardDescription>
          </CardHeader>
          <CardContent>
            {reputationQuery.isPending ? (
              <p className="text-sm text-slate-500">正在读取声望…</p>
            ) : null}
            {reputationQuery.isError ? (
              <p className="text-sm text-rose-600">{reputationError}</p>
            ) : null}
            {reputationQuery.data ? (
              <ReputationMeter reputation={reputationQuery.data} />
            ) : null}
          </CardContent>
        </Card>

        <PortraitPanel user={user} />

        <Card className="bg-white border-slate-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-bold text-slate-900">
              创作归档
            </CardTitle>
            <CardDescription className="text-xs text-slate-500">
              在你自己的知乎窗口里补抓正文。Verso 不读取知乎 Cookie。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link
              href="/archive"
              className={cn(buttonVariants({ size: "sm" }), "gap-1.5")}
            >
              打开归档工作台
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </CardContent>
        </Card>
      </div>
    </AppFrame>
  );
}
