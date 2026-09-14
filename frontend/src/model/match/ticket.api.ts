import { apiClient, unwrap } from "@/lib/http";
import type { StrengthTag } from "@/model/portrait";

export const ticketApi = {
  submitMatch: async (wantText: string, wantTag: StrengthTag) =>
    unwrap(
      await apiClient.POST("/match/conditions", {
        body: { want_text: wantText, want_tag: wantTag },
      }),
    ),
  currentMatch: async () => unwrap(await apiClient.GET("/match/conditions/me")),
  cancelMatch: async () =>
    unwrap(await apiClient.POST("/match/conditions/cancel")),
};
