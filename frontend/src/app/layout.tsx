import type { Metadata } from "next";
import localFont from "next/font/local";

import { BgmPlayer } from "@/components/bgm/BgmPlayer";
import { SetupGuard } from "@/components/setup/SetupGuard";
import { AppShell } from "@/components/shell/AppShell";
import { LlmConfigProvider } from "@/contexts/LlmConfigContext";
import "./globals.css";

// 字体文件本地打包（src/fonts/，来自 Google Fonts 官方 CDN，latin 子集，SIL OFL 授权可再分发），
// 不用 next/font/google：那个方案要在 `next build` 时联网下载字体，国内网络访问不到
// fonts.gstatic.com 会导致构建卡死重试、最终失败——「双击即玩」的核心承诺经不起这个依赖。
// 重新生成见 frontend/src/fonts/README.md。
const geistSans = localFont({
  src: "../fonts/geist-var.woff2",
  variable: "--font-geist-sans",
  weight: "100 900",
  display: "swap",
});

const geistMono = localFont({
  src: "../fonts/geist-mono-var.woff2",
  variable: "--font-geist-mono",
  weight: "100 900",
  display: "swap",
});

const notoSansSC = localFont({
  src: "../fonts/noto-sans-sc-var.woff2",
  variable: "--font-noto-zh",
  weight: "400 700",
  display: "swap",
  preload: false,
});

const fraunces = localFont({
  src: [
    { path: "../fonts/fraunces-normal-var.woff2", weight: "500 700", style: "normal" },
    { path: "../fonts/fraunces-italic-var.woff2", weight: "500 700", style: "italic" },
  ],
  variable: "--font-fraunces",
  display: "swap",
});

export const metadata: Metadata = {
  title: "心动实验室",
  description: "关系对话模拟产品",
};

// 在 HTML 解析阶段用普通 fetch()（高优先级）提前把首播曲目下入 HTTP 缓存。
// <link rel="preload" as="audio"> 被浏览器判为 Low 优先级，速度与媒体元素相当，无法解决问题。
// fetch() 与 JS/图片同优先级，写入 immutable 缓存后，<audio> 读缓存而非走低优先级网络通道。
// 静音时跳过，不浪费带宽。
const BGM_PRELOAD_SCRIPT = `(function(){try{
  if(localStorage.getItem('xindong:bgm:muted')==='true')return;
  var p=location.pathname;
  var src=p==='/setup'?'/bgm/login.mp3':p==='/personas/new'?'/bgm/persona-create.mp3':'/bgm/main-1.mp3';
  fetch(src).catch(function(){});
}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <head>
        <script dangerouslySetInnerHTML={{ __html: BGM_PRELOAD_SCRIPT }} />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${notoSansSC.variable} ${fraunces.variable} antialiased`}
      >
        <LlmConfigProvider>
          <SetupGuard>
            <AppShell withDesktopSidebar>{children}</AppShell>
          </SetupGuard>
          <BgmPlayer />
        </LlmConfigProvider>
      </body>
    </html>
  );
}
