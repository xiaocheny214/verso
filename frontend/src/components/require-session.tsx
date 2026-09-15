"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { AppFrame } from "@/components/app-frame";
import { useSession } from "@/components/use-session";

export function RequireSession({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { user, isPending } = useSession();

  useEffect(() => {
    if (!isPending && !user) {
      router.replace("/");
    }
  }, [isPending, user, router]);

  if (isPending) {
    return (
      <AppFrame>
        <p className="text-sm text-slate-500">正在确认登录…</p>
      </AppFrame>
    );
  }

  if (!user) {
    return (
      <AppFrame>
        <p className="text-sm text-slate-500">请先用知乎身份登录。</p>
      </AppFrame>
    );
  }

  return children;
}
