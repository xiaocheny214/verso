import { request } from "@/lib/http";

import type { ExchangeMessage } from "./message.type";

export const exchangeMessageApi = {
  messages: (id: string) =>
    request<ExchangeMessage[]>(`/exchanges/${id}/messages`),
  sendMessage: (id: string, text: string) =>
    request<ExchangeMessage>(`/exchanges/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
};
