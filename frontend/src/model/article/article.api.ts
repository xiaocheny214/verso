import { ApiError, apiClient, unwrap } from "@/lib/http";

export const articlesQueryKey = ["articles", "failed-fetch"] as const;

export const articleApi = {
  failedFetch: async () =>
    unwrap(await apiClient.GET("/me/articles/failed-fetch")),
  retryFetch: async () =>
    unwrap(await apiClient.POST("/me/articles/retry-fetch")),
};

export function isArticleGrantExpired(error: unknown): boolean {
  return error instanceof ApiError && error.code === 401;
}
