import { CheckCircle2 } from "lucide-react";
import type { MatchCondition } from "@/model/match";
import type { StrengthTag } from "@/model/portrait";

interface MatchExplanationProps {
  match: MatchCondition;
  myName: string;
  myStrengths: StrengthTag[];
}

export function MatchExplanation({
  match,
  myName,
  myStrengths,
}: MatchExplanationProps) {
  const peer = match.peer;
  if (!peer) return null;

  const myLabel = myName || "我";
  const myStrengthText =
    myStrengths.length > 0 ? myStrengths.join(" · ") : "画像生成中";

  return (
    <div className="space-y-6" aria-label="匹配成立原因">
      <div className="grid md:grid-cols-2 gap-6">
        {/* Person A: Me */}
        <div className="p-5 rounded-xl border border-slate-200 bg-slate-50 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs">
                {myLabel.slice(0, 1)}
              </div>
              <div>
                <span className="font-bold text-slate-900 text-sm block">
                  {myLabel}
                </span>
                <span className="text-xs text-slate-400 block">
                  能提供：{myStrengthText}
                </span>
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
                {peer.name.slice(0, 1)}
              </div>
              <div>
                <span className="font-bold text-slate-900 text-sm block">
                  {peer.name}
                </span>
                <span className="text-xs text-slate-400 block">
                  能提供：{(peer.strengths ?? []).join(" · ") || "画像生成中"}
                </span>
                <span className="text-xs text-slate-500 block">
                  声望 {peer.score}
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
            <span>
              {myLabel}的【{peer.want_tag}】能力覆盖{peer.name}的求教
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            <span>
              {peer.name}的【{match.want_tag}】能力覆盖{myLabel}的求教
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
