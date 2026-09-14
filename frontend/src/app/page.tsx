import Link from "next/link";
import {
  Compass,
  MessageSquare,
  Sparkles,
  ArrowRight,
  Clock,
} from "lucide-react";

import { AppFrame } from "@/components/app-frame";
import { ReciprocityMark } from "@/components/reciprocity-mark";
import { demoMatch } from "@/model/match";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "cn";

export default function Home() {
  const peer = demoMatch.peer!;

  return (
    <AppFrame>
      <div className="space-y-6">
        {/* Status Row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card className="bg-white border-slate-200">
            <CardHeader className="pb-2">
              <span className="text-xs text-slate-400 font-medium">
                知乎认证状态
              </span>
              <div className="flex items-center gap-2 pt-1">
                <span className="text-lg font-bold text-slate-900">已认证</span>
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-slate-500">林屿 · 知乎内容已连接</p>
            </CardContent>
          </Card>

          <Card className="bg-white border-slate-200">
            <CardHeader className="pb-2">
              <span className="text-xs text-slate-400 font-medium">
                翻开的叶（对局）
              </span>
              <div className="flex items-center gap-2 pt-1">
                <span className="text-lg font-bold text-slate-900">1 局进行中</span>
                <Badge variant="secondary" className="text-indigo-700 bg-indigo-50 border-indigo-200">
                  互答中
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-slate-500">对象：周衡（健身领域）</p>
            </CardContent>
          </Card>

          <Card className="bg-white border-slate-200">
            <CardHeader className="pb-2">
              <span className="text-xs text-slate-400 font-medium">
                沉淀能力画像
              </span>
              <div className="flex items-center gap-2 pt-1">
                <span className="text-lg font-bold text-slate-900">5 项能力</span>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-slate-500">互联网 · 编程 · 写作</p>
            </CardContent>
          </Card>
        </div>

        {/* Main Content: Current Match & Reciprocity Explainer */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            {/* Active Match Card */}
            <Card className="bg-white border-slate-200">
              <CardHeader className="pb-3 flex-row items-center justify-between space-y-0">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                  <CardTitle className="text-base font-bold text-slate-900">
                    当前对局 · 翻开的叶
                  </CardTitle>
                </div>
                <span className="text-xs text-slate-400 flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  21:34 截止
                </span>
              </CardHeader>

              <CardContent className="space-y-4">
                <div className="grid sm:grid-cols-2 gap-3">
                  <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100 text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-slate-400">对方为你解答</span>
                      <span className="font-bold text-emerald-700">周衡</span>
                    </div>
                    <p className="text-slate-700 font-medium line-clamp-2">
                      {demoMatch.want_text}
                    </p>
                  </div>

                  <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-100 text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-slate-400">你为对方解答</span>
                      <span className="font-bold text-indigo-700">林屿</span>
                    </div>
                    <p className="text-slate-700 font-medium line-clamp-2">
                      {peer.want_text}
                    </p>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-slate-400">
                    双方正在异步互答，窗口关闭前均可继续作答。
                  </span>
                  <Link
                    href="/exchange"
                    className={cn(buttonVariants({ size: "sm" }), "gap-1")}
                  >
                    <span>进入对局</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </div>
              </CardContent>
            </Card>

            {/* Reciprocity Explainer */}
            <Card className="bg-white border-slate-200">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-bold text-slate-900">
                  双向互补匹配原理
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ReciprocityMark />
              </CardContent>
            </Card>
          </div>

          {/* Right Column: Shortcuts */}
          <div className="space-y-4">
            <Card className="bg-white border-slate-200">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-bold text-slate-900">
                  快捷操作
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <Link
                  href="/match"
                  className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:border-slate-300 hover:bg-slate-50 transition-colors"
                >
                  <div className="flex items-center gap-2.5">
                    <Compass className="h-4 w-4 text-indigo-600" />
                    <div>
                      <div className="font-bold text-slate-800 text-xs">
                        发起匹配
                      </div>
                      <div className="text-slate-400 text-[11px]">
                        填写单次具体问题
                      </div>
                    </div>
                  </div>
                  <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                </Link>

                <Link
                  href="/exchange"
                  className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:border-slate-300 hover:bg-slate-50 transition-colors"
                >
                  <div className="flex items-center gap-2.5">
                    <MessageSquare className="h-4 w-4 text-emerald-600" />
                    <div>
                      <div className="font-bold text-slate-800 text-xs">
                        翻开的叶
                      </div>
                      <div className="text-slate-400 text-[11px]">
                        查看匹配对局
                      </div>
                    </div>
                  </div>
                  <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                </Link>

                <Link
                  href="/settings"
                  className="flex items-center justify-between p-3 rounded-lg border border-slate-100 hover:border-slate-300 hover:bg-slate-50 transition-colors"
                >
                  <div className="flex items-center gap-2.5">
                    <Sparkles className="h-4 w-4 text-purple-600" />
                    <div>
                      <div className="font-bold text-slate-800 text-xs">
                        设置
                      </div>
                      <div className="text-slate-400 text-[11px]">
                        登录认证与画像
                      </div>
                    </div>
                  </div>
                  <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                </Link>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </AppFrame>
  );
}
