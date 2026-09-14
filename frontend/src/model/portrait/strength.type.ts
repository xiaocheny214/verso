export type StrengthTag =
  | "编程"
  | "互联网"
  | "健身"
  | "训练"
  | "金融"
  | "写作"
  | "心理"
  | "教育";

export type PortraitSource = "contents" | "favorites" | "self_reported";
export type PortraitHorizon = "stable" | "recent_7d";

export interface Strength {
  tag: StrengthTag;
  source: PortraitSource;
  evidence_title?: string | null;
  evidence_url?: string | null;
}
