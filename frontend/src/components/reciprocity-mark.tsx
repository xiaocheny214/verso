import { CheckCircle2 } from "lucide-react";

export function ReciprocityMark() {
  return (
    <div className="p-6 rounded-xl bg-slate-50 border border-slate-200" aria-label="双向互补示意">
      <div className="grid sm:grid-cols-2 gap-4 items-center">
        {/* Person A */}
        <div className="p-4 rounded-lg bg-white border border-slate-200 shadow-2xs space-y-2">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs">
              林
            </div>
            <div>
              <span className="font-bold text-slate-900 text-xs block">林屿</span>
              <span className="text-[11px] text-slate-400 block">懂产品，想了解训练</span>
            </div>
          </div>
          <div className="pt-2 border-t border-slate-100 text-xs flex justify-between">
            <span className="text-slate-500">提供：<strong className="text-indigo-600">产品经验</strong></span>
            <span className="text-slate-400">想补：力量训练</span>
          </div>
        </div>

        {/* Person B */}
        <div className="p-4 rounded-lg bg-white border border-slate-200 shadow-2xs space-y-2">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 font-bold text-xs">
              周
            </div>
            <div>
              <span className="font-bold text-slate-900 text-xs block">周衡</span>
              <span className="text-[11px] text-slate-400 block">懂训练，想把经验做成产品</span>
            </div>
          </div>
          <div className="pt-2 border-t border-slate-100 text-xs flex justify-between">
            <span className="text-slate-500">提供：<strong className="text-emerald-600">训练经验</strong></span>
            <span className="text-slate-400">想补：互联网产品</span>
          </div>
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-slate-200/80 flex items-center justify-center gap-2 text-xs font-semibold text-indigo-700">
        <CheckCircle2 className="h-4 w-4 text-emerald-600" />
        <span>双向交叉覆盖成立：彼此恰好能回答对方的问题</span>
      </div>
    </div>
  );
}
