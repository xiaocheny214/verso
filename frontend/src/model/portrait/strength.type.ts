import type { components } from "@/lib/api/schema";

export type StrengthTag = components["schemas"]["StrengthTag"];
export type PortraitSource = components["schemas"]["PortraitSource"];
export type PortraitHorizon = components["schemas"]["PortraitHorizon"];
export type Strength = components["schemas"]["Strength"];

export const STRENGTH_TAGS = [
  "编程",
  "互联网",
  "健身",
  "运动训练",
  "职场",
  "学业",
  "理财",
  "写作",
  "设计",
  "医学健康",
  "法律",
  "其他",
] as const satisfies readonly StrengthTag[];
