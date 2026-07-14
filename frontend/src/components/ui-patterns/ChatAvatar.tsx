import Image from "next/image";
import { cn } from "@/lib/utils";

interface ChatAvatarProps {
  name: string;
  tone?: "character" | "assistant" | "user";
  size?: "sm" | "md" | "lg";
  online?: boolean;
  className?: string;
  imageSrc?: string;
}

const sizeClass = {
  sm: "size-8 rounded-xl text-xs",
  md: "size-10 rounded-2xl text-sm",
  lg: "size-12 rounded-2xl text-base",
};

const sizePx = { sm: 32, md: 40, lg: 48 };

const toneClass = {
  character: "text-white",
  assistant: "text-white",
  user: "bg-foreground/90 text-background",
};

export function ChatAvatar({ name, tone = "character", size = "md", className, imageSrc }: ChatAvatarProps) {
  const isUserTone = tone === "user";
  return (
    <div
      className={cn(
        "relative flex shrink-0 items-center justify-center overflow-hidden font-semibold ring-1 ring-white/60",
        isUserTone
          ? "shadow-sm"
          : "shadow-[0_2px_8px_-2px_oklch(0.68_0.20_42/0.30)]",
        sizeClass[size],
        toneClass[tone],
        className,
      )}
      style={isUserTone || imageSrc ? undefined : { background: "var(--brand-gradient)" }}
    >
      {imageSrc ? (
        <Image
          src={imageSrc}
          alt={name}
          width={sizePx[size]}
          height={sizePx[size]}
          className="size-full object-cover"
        />
      ) : (
        (name.trim().slice(0, 1) || "心").toUpperCase()
      )}
    </div>
  );
}
