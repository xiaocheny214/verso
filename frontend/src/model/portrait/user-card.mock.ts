import type { UserCard } from "./user-card.type";

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
