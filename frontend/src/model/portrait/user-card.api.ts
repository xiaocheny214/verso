import { apiClient, unwrap } from "@/lib/http";

export const userCardApi = {
  me: async () => unwrap(await apiClient.GET("/me")),
};
