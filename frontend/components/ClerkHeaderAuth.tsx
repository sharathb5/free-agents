"use client"

import * as React from "react"
import { useAuth, useClerk, UserButton } from "@clerk/nextjs"
import { cn } from "@/lib/utils"

export type ClerkHeaderAuthProps = {
  variant?: "hero" | "toolbar"
  /** Merged into `UserButton`; `afterSignOutUrl` is always set to `/` last. */
  userButtonProps?: React.ComponentProps<typeof UserButton>
}

/**
 * Header auth control that does not rely on SignInButton + custom children (can render empty in some setups).
 * Uses Clerk's imperative openSignIn for a reliable label and modal.
 */
export function ClerkHeaderAuth({ variant = "hero", userButtonProps }: ClerkHeaderAuthProps) {
  const { isLoaded, isSignedIn } = useAuth()
  const { openSignIn } = useClerk()

  const heroClass =
    "rounded-full border border-rock-blue/20 bg-pampas/8 px-4 py-2 text-xs font-semibold tracking-[0.18em] text-pampas/75 uppercase hover:bg-pampas/12 hover:text-pampas"
  const toolbarClass =
    "h-10 rounded-full px-4 text-sm font-medium transition-all border bg-pampas/5 text-pampas/75 border-rock-blue/15 hover:bg-pampas/8 hover:text-pampas"

  if (!isLoaded) {
    return (
      <span
        className={cn(
          "inline-flex items-center justify-center rounded-full border border-rock-blue/15 bg-pampas/8 text-pampas/60 tabular-nums",
          variant === "hero" ? "min-h-9 min-w-[5.5rem] px-4 py-2 text-xs font-semibold tracking-[0.18em] uppercase" : "h-10 min-w-[6rem] text-sm",
        )}
        aria-live="polite"
      >
        …
      </span>
    )
  }

  if (isSignedIn) {
    return <UserButton {...userButtonProps} afterSignOutUrl="/" />
  }

  return (
    <button
      type="button"
      onClick={() => openSignIn({})}
      className={variant === "hero" ? heroClass : toolbarClass}
    >
      Sign in
    </button>
  )
}
