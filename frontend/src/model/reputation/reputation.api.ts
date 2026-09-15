import { apiClient, isUnauthenticated, unwrap } from "@/lib/http";
import type { Reputation } from "./reputation.type";

export const reputationQueryKey = ["reputation", "me"] as const;

export const reputationApi = {
  me: async (): Promise<Reputation | null> => {
    try {
      return unwrap(await apiClient.GET("/me/reputation"));
    } catch (error) {
      if (isUnauthenticated(error)) {
        return null;
      }
      throw error;
    }
  },
};
