"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Archive, Library, MessageCircle, Settings, Trash2 } from "lucide-react";

export const primaryItems = [
  { href: "/", label: "会话", icon: MessageCircle },
  { href: "/personas", label: "人设库", icon: Library },
  { href: "/archive", label: "缘散录", icon: Archive },
  { href: "/archive/characters", label: "角色回收站", icon: Trash2 },
  { href: "/settings", label: "设置", icon: Settings },
];

export function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/" || pathname.startsWith("/characters/");
  if (href === "/personas") return pathname === "/personas" || pathname.startsWith("/personas/");
  return pathname === href;
}

export function DesktopSidebar() {
  const pathname = usePathname();

  return (
    <aside className="bg-card/90 border-border hidden border-r px-2 py-3 backdrop-blur-sm lg:flex lg:min-h-dvh lg:flex-col">
      <div className="flex flex-1 flex-col justify-between">
      <div className="space-y-2">
        <div className="flex justify-center pb-2">
          <Link href="/" aria-label="心动实验室首页" className="flex size-10 items-center justify-center">
            <Image
              src="/logo.png"
              alt="心动实验室"
              width={40}
              height={40}
              priority
              className="size-10 rounded-2xl"
            />
          </Link>
        </div>
        {primaryItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(pathname, item.href);
          return (
            <div key={item.href} className="relative flex justify-center">
              {/* 选中态：左侧渐变竖线（点线设计之「线」） */}
              {active && (
                <div
                  className="absolute inset-y-1.5 left-0 w-[3px] rounded-r-full"
                  style={{ background: "var(--brand-gradient)" }}
                  aria-hidden
                />
              )}
              <Link
                href={item.href}
                title={item.label}
                className={`flex size-11 items-center justify-center rounded-2xl transition-colors ${
                  active
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <Icon className="size-4.5" aria-hidden />
                <span className="sr-only">{item.label}</span>
              </Link>
            </div>
          );
        })}
      </div>
      </div>
    </aside>
  );
}
