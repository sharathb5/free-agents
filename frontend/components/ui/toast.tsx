import * as React from "react"
import { cn } from "@/lib/utils"

interface ToastProps {
  message: string
  isVisible: boolean
  onClose: () => void
}

export function Toast({ message, isVisible, onClose }: ToastProps) {
  React.useEffect(() => {
    if (isVisible) {
      const timer = setTimeout(() => {
        onClose()
      }, 2000)
      return () => clearTimeout(timer)
    }
  }, [isVisible, onClose])

  if (!isVisible) return null

  return (
    <div
      className={cn(
        "fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-xl border border-rock-blue/20 bg-blue-bayoux/95 px-4 py-3 text-sm text-pampas shadow-[0_24px_60px_-40px_rgba(159,178,205,0.55)] backdrop-blur transition-all duration-300",
        isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
      )}
    >
      <span>{message}</span>
    </div>
  )
}
