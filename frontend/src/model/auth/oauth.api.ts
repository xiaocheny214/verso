import { apiClient, unwrap } from "@/lib/http";

export const oauthApi = {
  authUrl: async () => unwrap(await apiClient.GET("/auth/zhihu/url")),
};
