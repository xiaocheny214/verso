import { apiClient, unwrap } from "@/lib/http";

export const exchangeListQueryKey = ["exchanges", "mine"] as const;

export const exchangeQueryKey = (exchangeId: string) =>
  ["exchanges", exchangeId] as const;

export const exchangeMessagesQueryKey = (exchangeId: string) =>
  ["exchanges", exchangeId, "messages"] as const;

export const exchangeSessionApi = {
  exchange: async (id: string) =>
    unwrap(
      await apiClient.GET("/exchanges/{exchange_id}", {
        params: { path: { exchange_id: id } },
      }),
    ),
  exchanges: async () => unwrap(await apiClient.GET("/exchanges/me")),
  closeExchange: async (id: string) =>
    unwrap(
      await apiClient.POST("/exchanges/{exchange_id}/close", {
        params: { path: { exchange_id: id } },
      }),
    ),
};
