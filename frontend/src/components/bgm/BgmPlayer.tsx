"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Volume2, VolumeX } from "lucide-react";

type BgmCategory = "login" | "persona-create" | "main";

const TARGET_VOLUME = 0.22;
const FADE_MS = 500;
const MUTED_STORAGE_KEY = "xindong:bgm:muted";
const UNMUTE_DELAY_MS = 300;

const MAIN_TRACKS = [
  "/bgm/main-1.mp3",
  "/bgm/main-2.mp3",
  "/bgm/main-3.mp3",
  "/bgm/main-4.mp3",
  "/bgm/main-5.mp3",
  "/bgm/main-6.mp3",
];

function categoryForPath(pathname: string): BgmCategory {
  if (pathname === "/login" || pathname === "/register") return "login";
  if (pathname === "/personas/new") return "persona-create";
  return "main";
}

function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function fadeAudio(
  audio: HTMLAudioElement,
  targetVol: number,
): { promise: Promise<void>; cancel: () => void } {
  let cancelled = false;
  const cancel = () => { cancelled = true; };
  const promise = new Promise<void>((resolve) => {
    const startVol = audio.volume;
    const startTime = performance.now();
    const step = (now: number) => {
      if (cancelled) { resolve(); return; }
      const progress = Math.min((now - startTime) / FADE_MS, 1);
      audio.volume = startVol + (targetVol - startVol) * progress;
      if (progress < 1) requestAnimationFrame(step);
      else resolve();
    };
    requestAnimationFrame(step);
  });
  return { promise, cancel };
}

// 以普通（高）优先级 fetch 把目标曲目完整下入 HTTP 缓存，而后 resolve。
// 浏览器对 <audio> 媒体请求使用 Low 优先级并限速；fetch() 与图片/脚本同优先级，
// 速度与界面资源相当。immutable 长缓存确保同 URL 再次请求直接命中缓存而不重下。
// 这正是"预热让切换无缝"背后的机制，现在也用于首播曲目。
async function warmFetch(src: string, signal?: AbortSignal): Promise<void> {
  try {
    const res = await fetch(src, signal ? { signal } : undefined);
    await res.blob(); // 消费响应体，确保缓存完整落盘
  } catch { /* AbortError 或网络错误，静默忽略 */ }
}


export function BgmPlayer() {
  const pathname = usePathname();

  const audioARef = useRef<HTMLAudioElement | null>(null);
  const audioBRef = useRef<HTMLAudioElement | null>(null);
  const activeSlotRef = useRef<"A" | "B">("A");

  const currentCategoryRef = useRef<BgmCategory | null>(null);
  const mainQueueRef = useRef<string[]>([]);
  const mainQueueIdxRef = useRef(0);

  const switchGenRef = useRef(0);
  const cancelFadesRef = useRef<Array<() => void>>([]);
  const unlockedRef = useRef(false);

  // 记录已预热过的 URL，避免重复 fetch
  const prewarmedRef = useRef<Set<string>>(new Set());
  // 所有后台预热 fetch 共用一个 AbortController；路由切换时 abort 让出带宽给前台曲目
  const prewarmAbortRef = useRef<AbortController | null>(null);

  const [isMuted, setIsMuted] = useState(false);

  const nextMainTrack = useCallback((): string => {
    if (mainQueueIdxRef.current >= mainQueueRef.current.length) {
      mainQueueRef.current = shuffle(MAIN_TRACKS);
      mainQueueIdxRef.current = 0;
    }
    return mainQueueRef.current[mainQueueIdxRef.current++];
  }, []);

  const trackForCategory = useCallback(
    (cat: BgmCategory): string => {
      if (cat === "login") return "/bgm/login.mp3";
      if (cat === "persona-create") return "/bgm/persona-create.mp3";
      return nextMainTrack();
    },
    [nextMainTrack],
  );

  // 利用浏览器空闲时间 fetch 预热目标 URL 进 HTTP 缓存。
  // 配合 /bgm/ 的长缓存头，预热过的曲目切页时直接命中缓存，几乎瞬时起播。
  // 每次路由切换时会 abort 所有在途预热，让前台曲目独占带宽；abort 后从已预热集合移除，
  // 使下次起播后能重新预热该曲目。
  const schedulePrewarm = useCallback((src: string) => {
    if (prewarmedRef.current.has(src)) return;
    prewarmedRef.current.add(src);
    // 捕获当前 controller，保证空闲回调触发时 abort 的是创建时那个批次
    const controller = prewarmAbortRef.current;
    const win = window as unknown as {
      requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => void;
    };
    const schedule = win.requestIdleCallback
      ? (cb: () => void) => win.requestIdleCallback!(cb, { timeout: 10000 })
      : (cb: () => void) => setTimeout(cb, 1000);
    schedule(() => {
      fetch(src, { signal: controller?.signal ?? undefined })
        .catch((err: Error) => {
          if (err?.name === "AbortError") prewarmedRef.current.delete(src);
        });
    });
  }, []);

  // 当前曲目起播后，在空闲时预热另外两个分类的曲目 + 主界面队列里的下一首，
  // 让页面切换时目标曲目已在缓存中。
  const prewarmOthers = useCallback((currentSrc: string, currentCat: BgmCategory) => {
    if (currentCat !== "login") schedulePrewarm("/bgm/login.mp3");
    if (currentCat !== "persona-create") schedulePrewarm("/bgm/persona-create.mp3");
    // 预热主界面队列下一首（当前是主界面时预热再下一首，否则预热第一首候选）
    const nextIdx = mainQueueIdxRef.current % mainQueueRef.current.length;
    const nextMain = mainQueueRef.current[nextIdx];
    if (nextMain && nextMain !== currentSrc) schedulePrewarm(nextMain);
  }, [schedulePrewarm]);

  // ── 初始化 ────────────────────────────────────────────────────────────

  useEffect(() => {
    const storedMuted = localStorage.getItem(MUTED_STORAGE_KEY) === "true";
    setIsMuted(storedMuted);

    const audioA = new Audio();
    const audioB = new Audio();
    [audioA, audioB].forEach((a) => {
      a.loop = false;
      a.preload = "auto";
      a.volume = 0;
    });
    audioARef.current = audioA;
    audioBRef.current = audioB;
    activeSlotRef.current = "A";

    prewarmAbortRef.current = new AbortController();

    // 首支固定 main-1，与 head 预加载脚本保持一致，确保预加载命中；后续仍随机
    const restMain = shuffle(MAIN_TRACKS.filter((t) => t !== "/bgm/main-1.mp3"));
    mainQueueRef.current = ["/bgm/main-1.mp3", ...restMain];
    mainQueueIdxRef.current = 0;

    const initialCategory = categoryForPath(window.location.pathname);
    currentCategoryRef.current = initialCategory;
    const initialSrc = trackForCategory(initialCategory);

    // warmFetch 以高优先级把首播曲目下入缓存（head 脚本已在 HTML 解析阶段提前开始）；
    // 完成后再设 src，让 <audio> 从缓存读取而非走低优先级网络通道。
    // 若 audio 已在播（gesture unlock 先触发），检测到后跳过，不重复起播。
    warmFetch(initialSrc, prewarmAbortRef.current?.signal ?? undefined).then(() => {
      if (!audioARef.current || !audioA.paused) return; // 已卸载或手势路径已起播
      // 无论是否静音都要设好 src，确保用户取消静音时 play() 可直接使用缓存
      audioA.src = initialSrc;
      audioA.load();
      if (storedMuted || unlockedRef.current) return;   // 静音或手势已解锁，不起播
      audioA.muted = true;
      audioA.play().then(() => {
        unlockedRef.current = true;
        const t = setTimeout(() => {
          if (!audioARef.current) return;
          audioA.muted = false;
          audioA.volume = 0;
          const { promise, cancel } = fadeAudio(audioA, TARGET_VOLUME);
          cancelFadesRef.current.push(cancel);
          promise.then(() => {
            cancelFadesRef.current = cancelFadesRef.current.filter((c) => c !== cancel);
            // 起播完成后，空闲时预热其他分类曲目
            prewarmOthers(initialSrc, initialCategory);
          });
        }, UNMUTE_DELAY_MS);
        return () => clearTimeout(t);
      }).catch(() => {
        audioA.muted = false;
      });
    });

    const unlock = () => {
      if (unlockedRef.current) return;
      unlockedRef.current = true;
      if (storedMuted) return;
      const active = activeSlotRef.current === "A" ? audioARef.current : audioBRef.current;
      if (!active) return;
      // warmFetch 可能仍在进行中（src 尚未设置）；此处确保手势路径也能正常起播
      if (!active.src) { active.src = initialSrc; active.load(); }
      active.muted = false;
      active.volume = 0;
      active.play().then(() => {
        const { promise, cancel } = fadeAudio(active, TARGET_VOLUME);
        cancelFadesRef.current.push(cancel);
        promise.then(() => {
          cancelFadesRef.current = cancelFadesRef.current.filter((c) => c !== cancel);
          prewarmOthers(initialSrc, initialCategory);
        });
      }).catch(() => {});
      document.removeEventListener("pointerdown", unlock);
      document.removeEventListener("keydown", unlock);
    };
    document.addEventListener("pointerdown", unlock);
    document.addEventListener("keydown", unlock);

    const makeEndedHandler = (slot: "A" | "B", audio: HTMLAudioElement) => () => {
      if (activeSlotRef.current !== slot) return;
      if (currentCategoryRef.current !== "main") return;
      if (localStorage.getItem(MUTED_STORAGE_KEY) === "true") return;
      const nextSrc = nextMainTrack();
      warmFetch(nextSrc, prewarmAbortRef.current?.signal ?? undefined).then(() => {
        if (activeSlotRef.current !== slot || currentCategoryRef.current !== "main") return;
        audio.src = nextSrc;
        audio.volume = 0;
        audio.load();
        audio.play().then(() => {
          const { promise, cancel } = fadeAudio(audio, TARGET_VOLUME);
          cancelFadesRef.current.push(cancel);
          promise.then(() => {
            cancelFadesRef.current = cancelFadesRef.current.filter((c) => c !== cancel);
            prewarmOthers(nextSrc, "main");
          });
        }).catch(() => {});
      }).catch(() => {});
    };
    const endedA = makeEndedHandler("A", audioA);
    const endedB = makeEndedHandler("B", audioB);
    audioA.addEventListener("ended", endedA);
    audioB.addEventListener("ended", endedB);

    return () => {
      audioA.removeEventListener("ended", endedA);
      audioB.removeEventListener("ended", endedB);
      document.removeEventListener("pointerdown", unlock);
      document.removeEventListener("keydown", unlock);
      cancelFadesRef.current.forEach((c) => c());
      prewarmAbortRef.current?.abort();
      audioA.pause();
      audioB.pause();
      audioARef.current = null;
      audioBRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── 路由切换：双缓冲淡入淡出 ─────────────────────────────────────────

  useEffect(() => {
    const storedMuted = localStorage.getItem(MUTED_STORAGE_KEY) === "true";
    const newCategory = categoryForPath(pathname);
    if (newCategory === currentCategoryRef.current) return;
    currentCategoryRef.current = newCategory;

    // 中断所有后台预热 fetch，把带宽完全让给前台正在等的这首曲目
    prewarmAbortRef.current?.abort();
    prewarmAbortRef.current = new AbortController();

    const newSrc = trackForCategory(newCategory);
    const gen = ++switchGenRef.current;

    const active = activeSlotRef.current === "A" ? audioARef.current : audioBRef.current;
    const inactive = activeSlotRef.current === "A" ? audioBRef.current : audioARef.current;
    if (!inactive) return;

    if (storedMuted || !unlockedRef.current) {
      // 静音/未解锁时也以高优先级暖缓存，确保切回时秒开
      warmFetch(newSrc, prewarmAbortRef.current?.signal ?? undefined).then(() => {
        if (switchGenRef.current !== gen) return;
        inactive.muted = false;
        inactive.volume = 0;
        inactive.src = newSrc;
        inactive.load();
        activeSlotRef.current = activeSlotRef.current === "A" ? "B" : "A";
      });
      return;
    }

    cancelFadesRef.current.forEach((c) => c());
    cancelFadesRef.current = [];

    let fadeOutCancel: (() => void) | null = null;
    const fadeOutPromise = active && !active.paused
      ? (() => {
          const { promise, cancel } = fadeAudio(active, 0);
          fadeOutCancel = cancel;
          return promise.then(() => { active.pause(); });
        })()
      : Promise.resolve();

    if (fadeOutCancel) cancelFadesRef.current.push(fadeOutCancel);

    // 以高优先级 warmFetch 暖缓存后再让 <audio> 从缓存起播，
    // 避免浏览器对媒体通道限速导致的数十秒等待。
    // 已被 prewarm 预热的曲目此处命中缓存近乎瞬时，不影响切换流畅度。
    const warmPromise = warmFetch(newSrc, prewarmAbortRef.current?.signal ?? undefined);

    Promise.all([fadeOutPromise, warmPromise]).then(() => {
      if (switchGenRef.current !== gen) return;
      inactive.muted = false;
      inactive.volume = 0;
      inactive.src = newSrc;
      inactive.load();
      activeSlotRef.current = activeSlotRef.current === "A" ? "B" : "A";
      const nowActive = activeSlotRef.current === "A" ? audioARef.current : audioBRef.current;
      if (!nowActive) return;
      nowActive.volume = 0;
      return nowActive.play().then(() => {
        const { promise, cancel } = fadeAudio(nowActive, TARGET_VOLUME);
        cancelFadesRef.current.push(cancel);
        promise.then(() => {
          cancelFadesRef.current = cancelFadesRef.current.filter((c) => c !== cancel);
          prewarmOthers(newSrc, newCategory);
        });
      });
    }).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  // ── 静音切换 ─────────────────────────────────────────────────────────

  const toggleMute = useCallback(async () => {
    const willMute = !isMuted;
    setIsMuted(willMute);
    localStorage.setItem(MUTED_STORAGE_KEY, String(willMute));

    cancelFadesRef.current.forEach((c) => c());
    cancelFadesRef.current = [];

    const active = activeSlotRef.current === "A" ? audioARef.current : audioBRef.current;
    const inactive = activeSlotRef.current === "A" ? audioBRef.current : audioARef.current;

    if (willMute) {
      if (active) {
        const { promise } = fadeAudio(active, 0);
        await promise;
        active.pause();
      }
      inactive?.pause();
    } else {
      unlockedRef.current = true;
      if (!active) return;
      active.muted = false;
      active.volume = 0;
      try {
        await active.play();
        const { promise } = fadeAudio(active, TARGET_VOLUME);
        await promise;
      } catch { /* ignore */ }
    }
  }, [isMuted]);

  // ── 渲染 ─────────────────────────────────────────────────────────────

  return (
    <button
      onClick={toggleMute}
      aria-label={isMuted ? "开启背景音乐" : "关闭背景音乐"}
      className="
        fixed left-4 bottom-20
        lg:bottom-4
        z-30
        w-8 h-8
        flex items-center justify-center
        rounded-full
        bg-white/30 backdrop-blur-sm
        text-neutral-500
        hover:bg-white/50 hover:text-neutral-700
        transition-colors duration-200
        shadow-sm
      "
    >
      {isMuted ? (
        <VolumeX className="w-3.5 h-3.5" />
      ) : (
        <Volume2 className="w-3.5 h-3.5" />
      )}
    </button>
  );
}
