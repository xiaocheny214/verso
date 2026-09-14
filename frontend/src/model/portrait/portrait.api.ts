import { request } from "@/lib/http";

import type { UserCard } from "./user-card.type";

export const portraitApi = {
  syncPortrait: () =>
    request<UserCard>("/me/portrait/sync", { method: "POST" }),
};
