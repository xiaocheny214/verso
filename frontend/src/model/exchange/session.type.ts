import type { StrengthTag } from "@/model/portrait";

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
