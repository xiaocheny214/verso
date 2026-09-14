"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Leaf, Settings } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "cn";

export const navItems = [
  { label: "匹配", href: "/match" },
  { label: "翻开的叶", href: "/exchange" },
] as const;

export function Header() {
  const pathname = usePathname();
  const isSettings = pathname === "/settings";

  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-200 bg-white/95 backdrop-blur-sm">
      <div className="grid h-14 grid-cols-[1fr_auto_1fr] items-center px-4 sm:px-6 lg:px-8">
        <Link
          href="/"
          className="justify-self-start flex items-center gap-2 font-bold text-slate-900 text-base hover:opacity-85 transition-opacity"
          aria-label="Verso 首页"
        >
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 text-white">
            <Leaf className="h-4 w-4 fill-current" />
          </div>
          <span>Verso</span>
        </Link>

        <nav className="justify-self-center flex items-center gap-1">
          {navItems.map((item) => {
            const isActive = pathname?.startsWith(item.href);

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                  isActive
                    ? "bg-slate-100 text-slate-900 font-semibold"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="justify-self-end flex items-center gap-2">
          <Link
            href="/settings"
            className={cn(
              buttonVariants({
                variant: isSettings ? "secondary" : "outline",
                size: "sm",
              }),
              "gap-1.5",
            )}
          >
            <Settings className="h-4 w-4" />
            <span>设置</span>
          </Link>
        </div>
      </div>
    </header>
  );
}
