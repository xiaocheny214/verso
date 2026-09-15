import { ApiError, apiClient, unwrap } from "@/lib/http";

import type { StrengthTag } from "./strength.type";

export const portraitApi = {
  syncPortrait: async () => unwrap(await apiClient.POST("/me/portrait/sync")),
  selfReport: async (tags: StrengthTag[]) =>
    unwrap(
      await apiClient.POST("/me/portrait/self-report", {
        body: { tags },
      }),
    ),
};

export function isPortraitGrantExpired(error: unknown): boolean {
  return error instanceof ApiError && error.code === 401;
}

export function isPortraitConflict(error: unknown): boolean {
  return error instanceof ApiError && error.code === 409;
}
