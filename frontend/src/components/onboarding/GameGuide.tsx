"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { EyeOff, Heart, HeartHandshake, Lock, MessageCircle, Sparkles, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { GUIDE_PENDING_STORAGE_KEY } from "@/components/onboarding/guide-storage";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui-patterns/StatusBadge";
import { cn } from "@/lib/utils";

/** 纯前端引导，不进后端、不影响存档。沿用项目 xindong: 前缀约定（参考 bgm:muted）。 */
const SEEN_STORAGE_KEY = "xindong:guide:seen";

/** 配置页本身不该弹「怎么玩」——玩家还没进游戏。 */
const HIDDEN_PATHS = ["/setup", "/login"];

interface GuideStep {
  icon: LucideIcon;
  iconClassName: string;
  title: string;
  description: string;
}

const STEPS: GuideStep[] = [
  {
    icon: Sparkles,
    iconClassName: "bg-amber-50 text-amber-600 ring-amber-100",
    title: "先捏一个想追求、想表白的对象",
    description:
      "可以是现实里让你心动的人，也可以完全是你想象出来的。跟「人设创建助手」聊几句，描述 ta 的性格、说话方式、在意什么、讨厌什么。也可以直接上传图片或文件（聊天记录、人物设定稿都行），助手会一起读进去，帮你把 ta 塑造得更像。",
  },
  {
    icon: MessageCircle,
    iconClassName: "bg-sky-50 text-sky-600 ring-sky-100",
    title: "从你设定的关系开始聊起",
    description:
      "你们是刚加上好友，还是认识很久的老同学，取决于你在人设里怎么写。开聊之后，这游戏不会给你任何好感度进度条，只能靠感觉去猜：ta 回得变长了还是变短了？主动问你问题了，还是敷衍两句就换话题？",
  },
];

export function GameGuide() {
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  // 一次会话只自动弹一次，避免 localStorage 写不进去时每次切页面都弹。
  const autoOpenedRef = useRef(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // 依赖 pathname：本组件挂在 AppShell 上，在配置页就已经 mount 了，但那时不该弹；
  // 要等玩家真正落到游戏内页面（配置完跳到「/」）才判断，所以不能只在 mount 时跑一次。
  useEffect(() => {
    if (!mounted || HIDDEN_PATHS.includes(pathname) || autoOpenedRef.current) return;
    try {
      // 刚配置完大模型：即使这个浏览器以前关过引导，也要再弹一次（这是玩家的「第一次进游戏」）。
      if (localStorage.getItem(GUIDE_PENDING_STORAGE_KEY)) {
        localStorage.removeItem(GUIDE_PENDING_STORAGE_KEY);
        autoOpenedRef.current = true;
        setOpen(true);
        return;
      }
      if (!localStorage.getItem(SEEN_STORAGE_KEY)) {
        autoOpenedRef.current = true;
        setOpen(true);
      }
    } catch {
      // 隐私模式等场景读不到 localStorage 就不强弹，玩家仍可点右下角问号手动打开
    }
  }, [mounted, pathname]);

  const close = () => {
    setOpen(false);
    try {
      localStorage.setItem(SEEN_STORAGE_KEY, "1");
    } catch {
      // 写不进去就下次再弹一次，不是什么大事
    }
  };

  if (!mounted || HIDDEN_PATHS.includes(pathname)) return null;

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="查看游戏玩法说明"
          title="怎么玩"
          className="fixed right-4 bottom-[calc(env(safe-area-inset-bottom)+4.75rem)] z-40 inline-flex size-11 items-center justify-center rounded-full text-white shadow-lg shadow-foreground/15 backdrop-blur transition-all hover:brightness-110 hover:scale-105 lg:bottom-6"
          style={{ background: "var(--brand-gradient)" }}
        >
          <span className="font-heading text-base leading-none font-semibold">?</span>
        </button>
      )}

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            aria-hidden="true"
            tabIndex={-1}
            className="absolute inset-0 bg-[oklch(0.20_0.025_200/0.4)] backdrop-blur-sm"
            onClick={close}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="game-guide-title"
            className="border-primary/15 bg-card relative z-10 flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-[1.75rem] border shadow-xl shadow-foreground/10"
          >
            {/* 头部：品牌渐变图标 + 衬线大标题，和站内其它页面标题的做法一致 */}
            <div className="relative shrink-0 overflow-hidden px-6 pt-6 pb-5">
              <div
                className="pointer-events-none absolute -top-16 -right-16 size-40 rounded-full opacity-[0.18] blur-2xl"
                style={{ background: "var(--brand-gradient)" }}
                aria-hidden
              />
              <button
                type="button"
                onClick={close}
                aria-label="关闭"
                className="text-muted-foreground hover:text-foreground hover:bg-muted absolute top-4 right-4 z-20 rounded-full p-1.5 transition-colors"
              >
                <X className="size-4" aria-hidden />
              </button>
              <div className="relative flex items-center gap-3">
                <span
                  className="inline-flex size-10 shrink-0 items-center justify-center rounded-2xl text-white shadow-sm"
                  style={{ background: "var(--brand-gradient)" }}
                  aria-hidden
                >
                  <Heart className="size-5" fill="currentColor" />
                </span>
                <div className="min-w-0">
                  <p className="font-heading text-muted-foreground text-[11px] font-medium tracking-[0.22em] uppercase italic">
                    新手引导
                  </p>
                  <h2 id="game-guide-title" className="font-heading text-foreground text-xl font-semibold tracking-tight">
                    怎么玩<span className="gradient-text">心动实验室</span>
                  </h2>
                </div>
              </div>
            </div>

            {/* 正文：可滚动，每一段都是图标 + 卡片，和结局卡片、消息面板同一套视觉语法 */}
            <div className="min-h-0 space-y-3 overflow-y-auto px-6 pb-2">
              {STEPS.map((step) => (
                <div key={step.title} className="border-border/60 bg-muted/30 flex gap-3 rounded-2xl border p-3.5">
                  <span
                    className={cn(
                      "inline-flex size-8 shrink-0 items-center justify-center rounded-xl ring-1",
                      step.iconClassName,
                    )}
                  >
                    <step.icon className="size-4" aria-hidden />
                  </span>
                  <div className="min-w-0 space-y-1">
                    <p className="text-foreground text-sm font-semibold">{step.title}</p>
                    <p className="text-muted-foreground text-xs leading-relaxed">{step.description}</p>
                  </div>
                </div>
              ))}

              <div className="border-border/60 bg-muted/30 rounded-2xl border p-3.5">
                <div className="flex gap-3">
                  <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 ring-1 ring-indigo-100">
                    <EyeOff className="size-4" aria-hidden />
                  </span>
                  <div className="min-w-0 space-y-1">
                    <p className="text-foreground text-sm font-semibold">隐藏状态在暗处变化</p>
                    <p className="text-muted-foreground text-xs leading-relaxed">
                      舒适感、兴趣度、信任感、警惕度……这些数字始终存在，但你永远看不到，只能从对话里去感觉。
                    </p>
                  </div>
                </div>
                <div className="mt-2.5 flex flex-wrap gap-1.5 pl-11">
                  {["舒适感", "兴趣度", "信任感", "警惕度"].map((label) => (
                    <StatusBadge key={label} tone="neutral">
                      <Lock className="mr-1 size-2.5" aria-hidden />
                      {label}
                    </StatusBadge>
                  ))}
                </div>
              </div>

              <div className="border-border/60 bg-muted/30 rounded-2xl border p-3.5">
                <div className="flex gap-3">
                  <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-xl bg-rose-50 text-rose-600 ring-1 ring-rose-100">
                    <HeartHandshake className="size-4" aria-hidden />
                  </span>
                  <div className="min-w-0 space-y-1">
                    <p className="text-foreground text-sm font-semibold">表白，揭晓结局</p>
                    <p className="text-muted-foreground text-xs leading-relaxed">
                      聊到你觉得是时候了，就鼓起勇气表白。游戏会根据这段关系一路走来的状态给你一个真正的结局，
                      并说清楚为什么走到了这一步。
                      <strong className="text-foreground">表白之后不能反悔重来</strong>
                      ——但同一个人设可以再捏一个新角色，重新开始一段新的故事。
                    </p>
                  </div>
                </div>
                <div className="mt-2.5 flex flex-wrap gap-1.5 pl-11">
                  <StatusBadge tone="neutral" className="bg-rose-50 text-rose-700 ring-rose-100">
                    幸福结局
                  </StatusBadge>
                  <StatusBadge tone="neutral" className="bg-amber-50 text-amber-700 ring-amber-100">
                    普通结局
                  </StatusBadge>
                  <StatusBadge tone="neutral" className="bg-indigo-50 text-indigo-700 ring-indigo-100">
                    遗憾结局
                  </StatusBadge>
                </div>
              </div>
            </div>

            <div className="border-border/60 bg-muted/20 mt-2 flex shrink-0 justify-end border-t px-6 py-4">
              <Button type="button" variant="hero" size="sm" className="rounded-full px-5" onClick={close}>
                明白啦，开始玩
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
