import { request } from "@/lib/http";

export const oauthApi = {
  authUrl: () => request<{ authorize_url: string }>("/auth/zhihu/url"),
};
