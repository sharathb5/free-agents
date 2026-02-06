import * as React from "react"

import { cn } from "@/lib/utils"

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-11 w-full rounded-xl border border-rock-blue/15 bg-pampas/6 px-4 py-2 text-sm text-pampas placeholder:text-pampas/45 shadow-[inset_0_1px_0_rgba(240,237,232,0.06)] ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-bayoux focus-visible:ring-offset-2 focus-visible:ring-offset-kilamanjaro disabled:cursor-not-allowed disabled:bg-pampas/6 disabled:text-pampas disabled:placeholder:text-pampas/45 disabled:opacity-100",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
