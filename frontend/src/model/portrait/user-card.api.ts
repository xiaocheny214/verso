import { request } from "@/lib/http";

import type { UserCard } from "./user-card.type";

export const userCardApi = {
  me: () => request<UserCard>("/me"),
};
