import { apiClient, unwrap } from "@/lib/http";

export const exchangeMessageApi = {
  messages: async (id: string) =>
    unwrap(
      await apiClient.GET("/exchanges/{exchange_id}/messages", {
        params: { path: { exchange_id: id } },
      }),
    ),
  sendMessage: async (id: string, text: string) =>
    unwrap(
      await apiClient.POST("/exchanges/{exchange_id}/messages", {
        params: { path: { exchange_id: id } },
        body: { text },
      }),
    ),
};
