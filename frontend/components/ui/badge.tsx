import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-blue-bayoux focus:ring-offset-2 focus:ring-offset-kilamanjaro",
  {
    variants: {
      variant: {
        default:
          "border-rock-blue/18 bg-blue-bayoux/35 text-pampas hover:bg-blue-bayoux/45",
        secondary:
          "border-rock-blue/18 bg-rock-blue/14 text-pampas hover:bg-rock-blue/18",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
        outline: "border-rock-blue/18 bg-pampas/6 text-pampas/80 hover:bg-pampas/10",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
