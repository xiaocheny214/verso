import { apiClient, isUnauthenticated, unwrap, unwrapVoid } from "@/lib/http";
import type { UserCard } from "@/model/portrait";

export const sessionQueryKey = ["auth", "me"] as const;

export const authApi = {
  authUrl: async () => unwrap(await apiClient.GET("/auth/zhihu/url")),
  logout: async () => {
    unwrapVoid(await apiClient.POST("/auth/logout"));
  },
  me: async (): Promise<UserCard | null> => {
    try {
      return unwrap(await apiClient.GET("/me"));
    } catch (error) {
      if (isUnauthenticated(error)) {
        return null;
      }
      throw error;
    }
  },
};
