import type {
  ExchangeMessage,
  MatchCondition,
  UserCard,
} from "@/lib/contracts";

export const demoUser: UserCard = {
  id: "user-linyu",
  name: "林屿",
  portraits: [
    {
      horizon: "stable",
      strengths: [
        {
          tag: "互联网",
          source: "contents",
          evidence_title: "从需求洞察到产品闭环",
        },
        {
          tag: "编程",
          source: "contents",
          evidence_title: "如何把一个想法做成可用的 Web 产品",
        },
        {
          tag: "写作",
          source: "favorites",
          evidence_title: "写作与表达收藏夹",
        },
      ],
    },
    {
      horizon: "recent_7d",
      strengths: [
        {
          tag: "互联网",
          source: "contents",
          evidence_title: "AI 产品需要怎样的反馈闭环",
        },
        {
          tag: "编程",
          source: "contents",
          evidence_title: "Agent 工具调用中的三个坑",
        },
      ],
    },
  ],
};

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

export const demoMessages: ExchangeMessage[] = [
  {
    id: "m1",
    exchange_id: "pair-verso-demo",
    sender_id: "user-zhouheng",
    text: "先不要追求动作数量。每周固定三次，把深蹲、俯卧撑和髋铰链各做三组；前两周只记录完成率，再按完成情况加量。",
    created_at: "2026-09-13T19:08:00+08:00",
  },
  {
    id: "m2",
    exchange_id: "pair-verso-demo",
    sender_id: "user-linyu",
    text: "先把你每天重复解释最多的问题做成一个最短流程，不急着做课程平台。用户每完成一次训练就留下一个可观察结果，这会成为迭代依据。",
    created_at: "2026-09-13T19:24:00+08:00",
  },
];
