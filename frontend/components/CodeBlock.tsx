"use client"

import * as React from "react"
import { Copy, Check } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface CodeBlockProps {
  code: string
  language?: string
  className?: string
  onCopy?: () => void
}

export function CodeBlock({ code, language, className, onCopy }: CodeBlockProps) {
  const [copied, setCopied] = React.useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
    onCopy?.()
  }

  return (
    <div className={cn("relative group", className)}>
      <pre className="overflow-x-auto rounded-xl bg-pampas/6 border border-rock-blue/15 p-4 text-sm shadow-[inset_0_1px_0_rgba(240,237,232,0.06)]">
        <code className="text-pampas/90 font-mono whitespace-pre">{code}</code>
      </pre>
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-2 right-2 h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity border border-rock-blue/15 bg-kilamanjaro/40 hover:bg-kilamanjaro/60"
        onClick={handleCopy}
        aria-label="Copy code"
      >
        {copied ? (
          <Check className="h-4 w-4 text-olive-green" />
        ) : (
          <Copy className="h-4 w-4 text-pampas/80" />
        )}
      </Button>
    </div>
  )
}
