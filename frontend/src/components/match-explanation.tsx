import { CheckCircle2 } from "lucide-react";
import type { MatchCondition } from "@/model/match";

export function MatchExplanation({ match }: { match: MatchCondition }) {
  const peer = match.peer;
  if (!peer) return null;

  return (
    <div className="space-y-6" aria-label="匹配成立原因">
      <div className="grid md:grid-cols-2 gap-6">
        {/* Person A: Me */}
        <div className="p-5 rounded-xl border border-slate-200 bg-slate-50 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs">
                林
              </div>
              <div>
                <span className="font-bold text-slate-900 text-sm block">林屿</span>
                <span className="text-xs text-slate-400 block">能提供：互联网 · 编程</span>
              </div>
            </div>
            <span className="text-xs px-2 py-0.5 rounded bg-indigo-100 text-indigo-800 font-semibold">
              想学：{match.want_tag}
            </span>
          </div>
          <div className="p-3 rounded-lg bg-white border border-slate-100 text-xs text-slate-800 font-medium">
            求教：“{match.want_text}”
          </div>
        </div>

        {/* Person B: Peer */}
        <div className="p-5 rounded-xl border border-slate-200 bg-slate-50 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 font-bold text-xs">
                周
              </div>
              <div>
                <span className="font-bold text-slate-900 text-sm block">{peer.name}</span>
                <span className="text-xs text-slate-400 block">
                  能提供：{peer.strengths.join(" · ")}
                </span>
              </div>
            </div>
            <span className="text-xs px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-semibold">
              想学：{peer.want_tag}
            </span>
          </div>
          <div className="p-3 rounded-lg bg-white border border-slate-100 text-xs text-slate-800 font-medium">
            求教：“{peer.want_text}”
          </div>
        </div>
      </div>

      {/* Dual Coverage Verification */}
      <div className="p-4 rounded-xl bg-indigo-50/70 border border-indigo-100 space-y-2 text-xs">
        <div className="flex items-center gap-2 text-indigo-950 font-semibold">
          <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          <span>双向互补条件已严格核验通过：</span>
        </div>
        <div className="grid sm:grid-cols-2 gap-2 text-indigo-900/80 pt-1">
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-500" />
            <span>林屿的【互联网】能力覆盖周衡的产品需求</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            <span>周衡的【健身】能力覆盖林屿的训练需求</span>
          </div>
        </div>
      </div>
    </div>
  );
}
