import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-bayoux focus-visible:ring-offset-2 focus-visible:ring-offset-kilamanjaro disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "bg-blue-bayoux text-pampas hover:bg-blue-bayoux/90 shadow-[0_10px_30px_-14px_rgba(159,178,205,0.35)]",
        success:
          "bg-olive-green text-kilamanjaro hover:bg-olive-green/90 shadow-[0_10px_30px_-14px_rgba(171,172,90,0.25)]",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline:
          "border border-rock-blue/20 bg-pampas/5 text-pampas hover:bg-pampas/8",
        secondary:
          "bg-pampas/8 text-pampas hover:bg-pampas/12 border border-rock-blue/15",
        ghost: "text-pampas/90 hover:bg-pampas/8 hover:text-pampas",
        link: "text-rock-blue underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
