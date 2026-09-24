import { ApiError, apiClient, unwrap } from "@/lib/http";

export const articlesQueryKey = ["articles"] as const;
export const articleQueueQueryKey = ["articles", "queue"] as const;

export const articleApi = {
  discover: async () => unwrap(await apiClient.POST("/me/articles/discover")),
  queue: async () => unwrap(await apiClient.GET("/me/articles/queue")),
  failedFetch: async () =>
    unwrap(await apiClient.GET("/me/articles/failed-fetch")),
};

export function isArticleGrantExpired(error: unknown): boolean {
  return error instanceof ApiError && error.code === 401;
}
