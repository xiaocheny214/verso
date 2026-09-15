import type { ReactNode } from "react";

import { RequireSession } from "@/components/require-session";

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return <RequireSession>{children}</RequireSession>;
}
