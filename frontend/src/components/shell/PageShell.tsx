"use client";

import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { ArrowUp } from "lucide-react";

import { FloatingScrollButton } from "@/components/ui-patterns/FloatingScrollButton";
import { cn } from "@/lib/utils";

interface PageShellProps {
  children: ReactNode;
  className?: string;
  size?: "md" | "lg" | "xl";
}

const sizeClass = {
  md: "max-w-4xl",
  lg: "max-w-6xl",
  xl: "max-w-7xl",
};

export function PageShell({ children, className, size = "lg" }: PageShellProps) {
  const scrollRef = useRef<HTMLElement | null>(null);
  const [showBackTop, setShowBackTop] = useState(false);

  useEffect(() => {
    const current = scrollRef.current;
    if (!current) return;
    const el = current;

    function onScroll(): void {
      setShowBackTop(el.scrollTop > 240);
    }

    onScroll();
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className={cn("relative mx-auto flex h-dvh min-h-0 w-full flex-col overflow-hidden px-4 py-4 pb-24 sm:px-6 md:py-8 lg:h-full lg:px-5 lg:pb-8", sizeClass[size], className)}>
      <main
        ref={scrollRef}
        className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto"
      >
        {children}
      </main>
      <FloatingScrollButton
        visible={showBackTop}
        label="回到顶部"
        className="fixed right-5 bottom-24 lg:bottom-8"
        onClick={() => scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" })}
      >
        <ArrowUp className="size-4" aria-hidden />
        顶部
      </FloatingScrollButton>
    </div>
  );
}
