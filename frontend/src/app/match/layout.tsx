import type { ReactNode } from "react";

import { RequireSession } from "@/components/require-session";

export default function MatchLayout({ children }: { children: ReactNode }) {
  return <RequireSession>{children}</RequireSession>;
}
