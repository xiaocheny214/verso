import type { Reputation } from "@/model/reputation";

function clampPercent(value: number, max: number): number {
  if (max <= 0) {
    return 0;
  }
  return Math.min(100, Math.max(0, (value / max) * 100));
}

function formatSuspendedUntil(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("zh-CN");
}

export function ReputationMeter({ reputation }: { reputation: Reputation }) {
  const scorePercent = clampPercent(reputation.score, reputation.score_max);
  const lockPercent = clampPercent(
    reputation.min_active_score,
    reputation.score_max,
  );
  const belowLock = reputation.score < reputation.min_active_score;

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-xs text-slate-400 font-medium">当前声望</p>
          <p className="text-2xl font-bold text-slate-900 tabular-nums">
            {reputation.score}
            <span className="ml-1 text-sm font-medium text-slate-400">
              / {reputation.score_max}
            </span>
          </p>
        </div>
        <p className="text-xs text-slate-500">
          锁定线 {reputation.min_active_score}
        </p>
      </div>

      <div className="space-y-1.5">
        <div className="relative h-3 rounded-full bg-slate-100 overflow-hidden">
          <div
            className="h-full rounded-full bg-indigo-600"
            style={{ width: `${scorePercent}%` }}
          />
          <div
            className="absolute inset-y-0 w-0.5 bg-rose-500"
            style={{ left: `${lockPercent}%` }}
            aria-hidden
          />
        </div>
        <div className="relative h-4 text-[11px] text-slate-400">
          <span className="absolute left-0">0</span>
          <span
            className="absolute -translate-x-1/2 text-rose-600"
            style={{ left: `${lockPercent}%` }}
          >
            锁定线
          </span>
          <span className="absolute right-0">{reputation.score_max}</span>
        </div>
      </div>

      {belowLock ? (
        <p className="text-xs text-rose-700">
          低于锁定线，暂时不能进入匹配。这不是封号，声望回升后即可再试。
        </p>
      ) : (
        <p className="text-xs text-slate-500">
          声望达到锁定线即可进入匹配池。页面只展示当前分，不会在浏览器里改分。
        </p>
      )}

      <p className="text-xs text-slate-400">
        资格状态 {reputation.eligibility}
      </p>
      {reputation.suspended_until ? (
        <p className="text-xs text-slate-400">
          暂停至 {formatSuspendedUntil(reputation.suspended_until)}
        </p>
      ) : null}
    </div>
  );
}
