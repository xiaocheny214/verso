import { apiClient, unwrap } from "@/lib/http";

export const qualityApi = {
  review: async (exchangeId: string) =>
    unwrap(
      await apiClient.POST("/reviews", {
        body: { exchange_id: exchangeId },
      }),
    ),
};
