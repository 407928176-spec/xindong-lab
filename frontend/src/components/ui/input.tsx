import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * 使用原生 `<input>` 而不是 `@base-ui/react/input`：
 * 当前项目里这是唯一使用点，且 Base UI 的 Input 实际走 `FieldControl` 的受控/事件合并链路，
 * 在「只想要一个普通输入框」场景更容易出现难排查的交互问题。
 * 人设创建页需要稳定可控的文本输入，因此这里保持 shadcn 的样式与 API（React input props）。
 */
const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  function Input({ className, type, ...props }, ref) {
    return (
      <input
        ref={ref}
        type={type}
        data-slot="input"
        className={cn(
          "h-8 w-full min-w-0 rounded-lg border border-input bg-[oklch(0.965_0.012_75)] px-2.5 py-1 text-base transition-colors outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm dark:bg-input/30 dark:disabled:bg-input/80 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
          className,
        )}
        {...props}
      />
    )
  },
)

export { Input }
