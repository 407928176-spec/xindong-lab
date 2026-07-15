# 本地字体文件

这 5 个 `.woff2` 是 Geist、Geist Mono、Fraunces、Noto Sans SC（仅 latin 子集）的官方变量字体文件，
直接从 Google Fonts CDN（`fonts.gstatic.com`）下载，SIL Open Font License 1.1 授权，允许免费再分发。

## 为什么不用 `next/font/google`

那个方案会在 `next build` 时联网向 `fonts.gstatic.com` 下载字体文件。国内网络访问不到这个域名，
构建会卡在 `Retrying 1/3...` 反复重试，最终失败——这个项目的核心承诺是「下载即玩」，构建这一步
不该有任何外部网络依赖。改用 `next/font/local` 直接从仓库里的文件读取，构建完全离线可行。

## 文件从哪来 / 怎么重新生成

字号范围要和 `frontend/src/app/layout.tsx` 里 `localFont()` 的 `weight` 参数对应。用一个现代浏览器
的 User-Agent 请求 Google 的 CSS2 接口，只取 `latin` 子集的 `@font-face` 块，里面的 URL 就是要下载
的文件：

```bash
curl -s "https://fonts.googleapis.com/css2?family=Geist:wght@100..900&family=Geist+Mono:wght@100..900&family=Noto+Sans+SC:wght@400;500;700&family=Fraunces:ital,wght@0,500;0,600;0,700;1,500;1,600;1,700&display=swap" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
```

响应里按 `/* latin */` 注释分块，只取这一块下面的 `@font-face`；其余 `vietnamese` / `latin-ext` 等
子集不需要。四个字体族都是变量字体，同一字重区间的多条声明会指向同一个文件 URL，下载一次即可。

## 什么时候需要重新生成

- 想换成别的字体族或字重范围。
- 上游字体发布了新版本（文件名里的版本号，如 `fraunces/v38`，变了）。

日常开发、换别的功能不需要碰这个目录。
