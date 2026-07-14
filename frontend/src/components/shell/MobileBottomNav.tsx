"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { isActive, primaryItems } from "@/components/shell/DesktopSidebar";

export function MobileBottomNav() {
  const pathname = usePathname();
  const items = primaryItems;

  return (
    <nav className="border-border bg-card/92 fixed inset-x-0 bottom-0 z-40 border-t px-2 pb-[calc(env(safe-area-inset-bottom)+0.5rem)] pt-2 shadow-[0_-8px_30px_rgba(15,23,42,0.06)] backdrop-blur lg:hidden">
      <div className="grid grid-cols-5 gap-1">
        {items.map((item) => {
          const Icon = item.icon;
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex flex-col items-center justify-center gap-1 rounded-2xl px-1.5 py-2 text-[11px] font-medium transition-colors ${
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <Icon className="size-4" aria-hidden />
              {item.href === "/archive/characters" ? (
                <span className="flex flex-wrap items-center justify-center leading-tight">
                  <span>角色</span>
                  <span>回收站</span>
                </span>
              ) : (
                <span>{item.label}</span>
              )}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
