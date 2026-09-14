import { request } from "@/lib/http";
import type { StrengthTag } from "@/model/portrait";

import type { MatchCondition } from "./ticket.type";

export const ticketApi = {
  submitMatch: (wantText: string, wantTag: StrengthTag) =>
    request<MatchCondition>("/match/conditions", {
      method: "POST",
      body: JSON.stringify({ want_text: wantText, want_tag: wantTag }),
    }),
  currentMatch: () => request<MatchCondition>("/match/conditions/me"),
  cancelMatch: () =>
    request<MatchCondition>("/match/conditions/cancel", { method: "POST" }),
};
