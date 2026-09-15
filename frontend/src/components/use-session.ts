"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { authApi, sessionQueryKey } from "@/model/auth";

export function useSession() {
  const query = useQuery({
    queryKey: sessionQueryKey,
    queryFn: authApi.me,
    retry: false,
  });

  return {
    ...query,
    user: query.data ?? null,
    isAuthenticated: query.data != null,
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
