"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { GameGuide } from "@/components/onboarding/GameGuide";
import { DesktopSidebar } from "@/components/shell/DesktopSidebar";
import { MobileBottomNav } from "@/components/shell/MobileBottomNav";
import { cn } from "@/lib/utils";

interface AppShellProps {
  children: ReactNode;
  className?: string;
  withDesktopSidebar?: boolean;
  withMobileNav?: boolean;
}

export function AppShell({ children, className, withDesktopSidebar = false, withMobileNav = true }: AppShellProps) {
  const pathname = usePathname();
  const isLoginPage = pathname === "/login";
  const showDesktopSidebar = withDesktopSidebar && !isLoginPage;
  const showMobileNav = withMobileNav && !isLoginPage;

  return (
    <div className={cn("min-h-dvh bg-app text-foreground", className)}>
      {/* 品牌渐变光环：金橘（左上）+ 深橙（右下），常驻氛围层 */}
      <div
        className="aura-mint pointer-events-none fixed -left-48 -top-48 z-0 h-[600px] w-[600px] rounded-full opacity-[0.22]"
        style={{ background: "oklch(0.86 0.14 68)", filter: "blur(100px)" }}
        aria-hidden
      />
      <div
        className="aura-coral pointer-events-none fixed -bottom-48 -right-48 z-0 h-[600px] w-[600px] rounded-full opacity-[0.20]"
        style={{ background: "oklch(0.68 0.20 42)", filter: "blur(110px)" }}
        aria-hidden
      />
      {showDesktopSidebar ? (
        <div className="lg:grid lg:h-dvh lg:min-h-0 lg:grid-cols-[4.5rem_minmax(0,1fr)] lg:overflow-hidden">
          <DesktopSidebar />
          <div className="relative z-10 min-w-0 lg:h-dvh lg:min-h-0 lg:overflow-hidden">{children}</div>
        </div>
      ) : (
        <div className="relative z-10">{children}</div>
      )}
      {showMobileNav ? <MobileBottomNav /> : null}
      <GameGuide />
    </div>
  );
}
