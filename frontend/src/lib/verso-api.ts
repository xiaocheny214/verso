import type {
  ApiResponse,
  Exchange,
  ExchangeMessage,
  MatchCondition,
  Pair,
  StrengthTag,
  UserCard,
} from "@/lib/contracts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  const envelope = (await response.json()) as ApiResponse<T>;
  if (envelope.code !== 200) {
    throw new Error(envelope.message || "请求失败");
  }
  return envelope.data;
}

export const versoApi = {
  authUrl: () => request<{ authorize_url: string }>("/auth/zhihu/url"),
  me: () => request<UserCard>("/me"),
  syncPortrait: () =>
    request<UserCard>("/me/portrait/sync", { method: "POST" }),
  submitMatch: (wantText: string, wantTag: StrengthTag) =>
    request<MatchCondition>("/match/conditions", {
      method: "POST",
      body: JSON.stringify({ want_text: wantText, want_tag: wantTag }),
    }),
  currentMatch: () => request<MatchCondition>("/match/conditions/me"),
  cancelMatch: () =>
    request<MatchCondition>("/match/conditions/cancel", { method: "POST" }),
  exchange: (id: string) => request<Exchange>(`/exchanges/${id}`),
  exchanges: () => request<Pair[]>("/exchanges/me"),
  messages: (id: string) =>
    request<ExchangeMessage[]>(`/exchanges/${id}/messages`),
  sendMessage: (id: string, text: string) =>
    request<ExchangeMessage>(`/exchanges/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  closeExchange: (id: string) =>
    request<Exchange>(`/exchanges/${id}/close`, { method: "POST" }),
};
