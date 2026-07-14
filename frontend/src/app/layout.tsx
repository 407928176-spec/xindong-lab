import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono, Noto_Sans_SC } from "next/font/google";

import { BgmPlayer } from "@/components/bgm/BgmPlayer";
import { SetupGuard } from "@/components/setup/SetupGuard";
import { AppShell } from "@/components/shell/AppShell";
import { LlmConfigProvider } from "@/contexts/LlmConfigContext";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const notoSansSC = Noto_Sans_SC({
  variable: "--font-noto-zh",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  display: "swap",
  preload: false,
});

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  style: ["normal", "italic"],
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
