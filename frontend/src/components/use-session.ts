"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { authApi, sessionQueryKey } from "@/model/auth";
import type { UserCard } from "@/model/portrait";

function portraitLooksEmpty(user: UserCard | null | undefined): boolean {
  if (!user) {
    return false;
  }
  const portraits = user.portraits ?? [];
  if (portraits.length === 0) {
    return true;
  }
  return portraits.every((portrait) => (portrait.strengths ?? []).length === 0);
}

export function useSession() {
  const query = useQuery({
    queryKey: sessionQueryKey,
    queryFn: authApi.me,
    retry: false,
    refetchInterval: (q) => (portraitLooksEmpty(q.state.data) ? 4000 : false),
  });

  return {
    ...query,
    user: query.data ?? null,
    isAuthenticated: query.data != null,
    portraitPending: portraitLooksEmpty(query.data),
  };
}

export function useZhihuLogin() {
  return useMutation({
    mutationFn: authApi.authUrl,
    onSuccess: ({ authorize_url }) => {
      window.location.assign(authorize_url);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation({
    mutationFn: authApi.logout,
    onSuccess: () => {
      queryClient.setQueryData(sessionQueryKey, null);
      router.replace("/");
    },
  });
}
