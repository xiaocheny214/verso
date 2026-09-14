import { request } from "@/lib/http";

import type { Exchange, Pair } from "./session.type";

export const exchangeSessionApi = {
  exchange: (id: string) => request<Exchange>(`/exchanges/${id}`),
  exchanges: () => request<Pair[]>("/exchanges/me"),
  closeExchange: (id: string) =>
    request<Exchange>(`/exchanges/${id}/close`, { method: "POST" }),
};
