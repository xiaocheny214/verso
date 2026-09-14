import type { StrengthTag } from "@/model/portrait";

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
