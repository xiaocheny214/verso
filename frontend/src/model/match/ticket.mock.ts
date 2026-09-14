import type { MatchCondition } from "./ticket.type";

export const demoMatch: MatchCondition = {
  id: "condition-linyu",
  want_text: "没有器械，怎样制定一套能坚持三个月的力量训练计划？",
  want_tag: "健身",
  status: "matched",
  pair_id: "pair-verso-demo",
  waiting_until: "2026-09-14T20:00:00+08:00",
  pair_closes_at: "2026-09-14T20:00:00+08:00",
  peer: {
    id: "user-zhouheng",
    name: "周衡",
    want_text: "怎样把线下训练经验做成一个有人持续使用的互联网产品？",
    want_tag: "互联网",
    strengths: ["健身", "训练"],
  },
};
