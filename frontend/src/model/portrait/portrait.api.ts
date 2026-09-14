import { apiClient, unwrap } from "@/lib/http";

export const portraitApi = {
  syncPortrait: async () => unwrap(await apiClient.POST("/me/portrait/sync")),
};
