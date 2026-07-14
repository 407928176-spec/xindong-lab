"use client";

import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

const markdownComponents: Components = {
  a: ({ href, children, className, ...props }) => (
    <a
      href={href}
      className={cn("text-primary underline underline-offset-2", className)}
      target="_blank"
      rel="noopener noreferrer"
      {...props}
    >
      {children}
    </a>
  ),
  p: ({ children, className, ...props }) => (
    <p className={cn("mb-2 text-sm leading-relaxed last:mb-0", className)} {...props}>
      {children}
    </p>
  ),
  ul: ({ children, className, ...props }) => (
    <ul className={cn("mb-2 list-disc pl-5 text-sm leading-relaxed last:mb-0", className)} {...props}>
      {children}
    </ul>
  ),
  ol: ({ children, className, ...props }) => (
    <ol className={cn("mb-2 list-decimal pl-5 text-sm leading-relaxed last:mb-0", className)} {...props}>
      {children}
    </ol>
  ),
  li: ({ children, className, ...props }) => (
    <li className={cn("mt-1 first:mt-0", className)} {...props}>
      {children}
    </li>
  ),
  h1: ({ children, className, ...props }) => (
    <h1 className={cn("mb-2 mt-3 text-base font-semibold first:mt-0", className)} {...props}>
      {children}
    </h1>
  ),
  h2: ({ children, className, ...props }) => (
    <h2 className={cn("mb-2 mt-3 text-sm font-semibold first:mt-0", className)} {...props}>
      {children}
    </h2>
  ),
  h3: ({ children, className, ...props }) => (
    <h3 className={cn("mb-1 mt-2 text-sm font-semibold first:mt-0", className)} {...props}>
      {children}
    </h3>
  ),
  blockquote: ({ children, className, ...props }) => (
    <blockquote
      className={cn(
        "border-primary/40 text-muted-foreground my-2 border-l-2 py-0.5 pl-3 text-sm italic",
        className,
      )}
      {...props}
    >
      {children}
    </blockquote>
  ),
  hr: ({ className, ...props }) => (
    <hr className={cn("border-border my-3 border-t", className)} {...props} />
  ),
  pre: ({ children, className, ...props }) => (
    <pre
      className={cn(
        "bg-muted text-foreground my-2 overflow-x-auto rounded-md border border-border p-2 font-mono text-xs leading-relaxed",
        className,
      )}
      {...props}
    >
      {children}
    </pre>
  ),
  code: ({ className, children, ...props }) => {
    const isBlock = typeof className === "string" && className.includes("language-");
    if (isBlock) {
      return (
        <code className={cn("block whitespace-pre font-mono", className)} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code
        className={cn(
          "bg-muted text-foreground rounded px-1 py-0.5 font-mono text-[0.85em] leading-none",
          className,
        )}
        {...props}
      >
        {children}
      </code>
    );
  },
  table: ({ children, className, ...props }) => (
    <div className="my-2 max-w-full overflow-x-auto">
      <table className={cn("border-border w-full min-w-[240px] border-collapse border text-xs", className)} {...props}>
        {children}
      </table>
    </div>
  ),
  thead: ({ children, className, ...props }) => (
    <thead className={cn("bg-muted/60", className)} {...props}>
      {children}
    </thead>
  ),
  th: ({ children, className, ...props }) => (
    <th className={cn("border-border px-2 py-1.5 text-left font-semibold", className)} {...props}>
      {children}
    </th>
  ),
  td: ({ children, className, ...props }) => (
    <td className={cn("border-border px-2 py-1.5 align-top", className)} {...props}>
      {children}
    </td>
  ),
  tr: ({ className, ...props }) => <tr className={cn("border-border border-t first:border-t-0", className)} {...props} />,
  img: ({ alt, className, ...props }) => (
    // eslint-disable-next-line @next/next/no-img-element -- assistant Markdown may contain remote URLs from model
    <img alt={alt ?? ""} className={cn("my-2 h-auto max-w-full rounded-md", className)} {...props} />
  ),
  strong: ({ children, className, ...props }) => (
    <strong className={cn("font-semibold", className)} {...props}>
      {children}
    </strong>
  ),
  del: ({ children, className, ...props }) => (
    <del className={cn("text-muted-foreground", className)} {...props}>
      {children}
    </del>
  ),
};

interface AssistantMarkdownProps {
  /** 人设创建助手回复原文（Markdown）。 */
  content: string;
}

/**
 * 人设创建助手气泡专用：GFM（表格、删除线等）+ 紧凑 Tailwind 样式，不启用 HTML 原始片段解析。
 */
export function AssistantMarkdown({ content }: AssistantMarkdownProps) {
  const trimmed = content.trim();
  if (!trimmed) {
    return <span className="text-muted-foreground text-sm italic">（空消息）</span>;
  }

  return (
    <div className="[&_*]:break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {trimmed}
      </ReactMarkdown>
    </div>
  );
}
