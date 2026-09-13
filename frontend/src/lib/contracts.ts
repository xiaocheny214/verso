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

export interface Portrait {
  horizon: PortraitHorizon;
  strengths: Strength[];
}

export interface UserCard {
  id: string;
  name: string;
  avatar_url?: string | null;
  portraits: Portrait[];
}

export type MatchStatus = "waiting" | "matched" | "cancelled";

export interface MatchPeer {
  id: string;
  name: string;
  avatar_url?: string | null;
  want_text: string;
  want_tag: StrengthTag;
  strengths: StrengthTag[];
}

export interface MatchCondition {
  id: string;
  want_text: string;
  want_tag: StrengthTag;
  status: MatchStatus;
  pair_id?: string | null;
  waiting_until?: string | null;
  pair_closes_at?: string | null;
  peer?: MatchPeer | null;
}

export type ExchangeStatus = "open" | "closed";

export interface Pair {
  exchange_id: string;
  peer_id: string;
  peer_name: string;
  peer_avatar_url?: string | null;
  peer_strengths: StrengthTag[];
  peer_want_text: string;
}

export interface Exchange {
  id: string;
  user_a_id: string;
  user_b_id: string;
  status: ExchangeStatus;
  opened_at: string;
  closes_at: string;
  closed_at?: string | null;
}

export interface ExchangeMessage {
  id: string;
  exchange_id: string;
  sender_id: string;
  text: string;
  created_at: string;
}

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}
