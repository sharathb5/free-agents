"use client"

import * as React from "react"
import { ExternalLink } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  buildClaudeNewChatUrl,
  buildCursorPromptDeeplink,
  buildCursorPromptText,
  shouldWarnAboutIdeCustomLinks,
  type AgentIdeContextInput,
} from "@/lib/agent-ide-context"
import { cn } from "@/lib/utils"

interface OpenInIdeButtonsProps {
  ideContext: AgentIdeContextInput | null
  className?: string
  variant?: "outline" | "default"
  size?: "default" | "sm"
}

export function OpenInIdeButtons({
  ideContext,
  className,
  variant = "outline",
  size = "default",
}: OpenInIdeButtonsProps) {
  const [warnCustom, setWarnCustom] = React.useState(false)
  React.useEffect(() => {
    setWarnCustom(shouldWarnAboutIdeCustomLinks())
  }, [])

  const cursorHref = React.useMemo(
    () => (ideContext ? buildCursorPromptDeeplink(buildCursorPromptText(ideContext)) : "#"),
    [ideContext]
  )
  const claudeHref = React.useMemo(
    () => (ideContext ? buildClaudeNewChatUrl(ideContext) : "#"),
    [ideContext]
  )

  const cursorUnsupportedTitle = warnCustom
    ? "This environment often blocks cursor:// app links. Try Chrome, Edge, or desktop Safari, confirm the “Open Cursor” prompt, or copy context from the page."
    : undefined

  if (!ideContext) return null

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <Button variant={variant} size={size} asChild>
        <a
          href={cursorHref}
          title={cursorUnsupportedTitle}
          aria-label="Open in Cursor with agent context prefilled using the official prompt deeplink"
        >
          Open in Cursor
        </a>
      </Button>
      <Button variant={variant} size={size} asChild>
        <a
          href={claudeHref}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="Open Claude on the web with agent context prefilled"
        >
          Open in Claude
          <ExternalLink className="ml-2 h-3.5 w-3.5 opacity-70" aria-hidden />
        </a>
      </Button>
    </div>
  )
}
