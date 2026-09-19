import { ApiError, apiClient, unwrap } from "@/lib/http";
import type { StrengthTag } from "@/model/portrait";

import type { MatchCondition } from "./ticket.type";

export const matchQueryKey = ["match", "current"] as const;

export const ticketApi = {
  submitMatch: async (wantText: string, wantTag: StrengthTag) =>
    unwrap(
      await apiClient.POST("/match/conditions", {
        body: { want_text: wantText, want_tag: wantTag },
      }),
    ),
  currentMatch: async (): Promise<MatchCondition | null> => {
    try {
      return unwrap(await apiClient.GET("/match/conditions/me"));
    } catch (error) {
      if (error instanceof ApiError && error.code === 404) {
        return null;
      }
      throw error;
    }
  },
  cancelMatch: async () =>
    unwrap(await apiClient.POST("/match/conditions/cancel")),
};

export function isMatchIneligible(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.code === 409 &&
    error.message === "当前不能配对"
  );
}
