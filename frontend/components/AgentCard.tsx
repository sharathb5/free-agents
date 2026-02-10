"use client"

import * as React from "react"
import { Copy } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { AgentSummary } from "@/lib/agents"
import { cn } from "@/lib/utils"

interface AgentCardProps {
  agent: AgentSummary
  onClick: () => void
  onCopy?: () => void
}

const primitiveColors: Record<string, string> = {
  transform: "bg-blue-bayoux/18 text-pampas border-rock-blue/20",
  extract: "bg-rock-blue/16 text-pampas border-rock-blue/20",
  classify: "bg-pampas/8 text-pampas border-rock-blue/20",
}

const primitiveGlow: Record<string, { border: string; glow: string }> = {
  transform: {
    border: "rgba(73, 102, 119, 0.40)", // blue-bayoux
    glow: "rgba(73, 102, 119, 0.28)",
  },
  extract: {
    border: "rgba(159, 178, 205, 0.38)", // rock-blue
    glow: "rgba(159, 178, 205, 0.24)",
  },
  classify: {
    border: "rgba(171, 172, 90, 0.34)", // olive-green (sparingly)
    glow: "rgba(171, 172, 90, 0.18)",
  },
}

export function AgentCard({ agent, onClick, onCopy }: AgentCardProps) {
  const installCommand = `AGENT_PRESET=${agent.id} agent-toolbox`
  const copyInstall = async (e: React.MouseEvent) => {
    e.stopPropagation()
    await navigator.clipboard.writeText(installCommand)
    onCopy?.()
  }

  const glow = primitiveGlow[agent.primitive] ?? primitiveGlow.transform

  return (
    <Card
      className={cn(
        "group relative cursor-pointer transition-all hover:-translate-y-1 overflow-hidden h-full",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-bayoux focus-visible:ring-offset-2 focus-visible:ring-offset-kilamanjaro"
      )}
      style={{
        borderColor: glow.border,
        boxShadow: `0 28px 70px -52px ${glow.glow}`,
      }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onClick()
        }
      }}
    >
      {/* Subtle highlight wash (tag/primitive-based) */}
      <div
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{
          background: `radial-gradient(600px circle at 20% 0%, ${glow.glow}, transparent 55%)`,
        }}
      />

      {/* Content */}
      <div className="relative flex h-full min-h-[260px] flex-col">
        <CardHeader>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <CardTitle className="text-xl mb-2 tracking-tight">{agent.name}</CardTitle>
              <CardDescription className="text-sm line-clamp-2">
                {agent.description}
              </CardDescription>
              {agent.credits?.name && (
                <div className="mt-2 text-xs text-pampas/60">
                  Created by{" "}
                  {agent.credits.url ? (
                    <a
                      href={agent.credits.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-rock-blue underline hover:text-pampas"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {agent.credits.name}
                    </a>
                  ) : (
                    <span className="text-pampas/75">{agent.credits.name}</span>
                  )}
                </div>
              )}
            </div>
          </div>
        </CardHeader>

        <CardContent className="flex-1">
          <div className="flex flex-col gap-3">
            <div className="flex min-h-[28px] items-center gap-2 flex-wrap">
              <Badge
                variant="secondary"
                className={cn(
                  "text-xs font-medium border",
                  primitiveColors[agent.primitive] || primitiveColors.transform
                )}
              >
                {agent.primitive}
              </Badge>
              {agent.archived && (
                <Badge
                  variant="outline"
                  className="text-xs border-amber-400/40 bg-amber-500/10 text-amber-200"
                >
                  archived
                </Badge>
              )}
              {(agent.tags || []).slice(0, 2).map((tag) => (
                <Badge
                  key={tag}
                  variant="outline"
                  className="text-xs border-rock-blue/20 bg-pampas/6 text-pampas/75"
                >
                  {tag}
                </Badge>
              ))}
            </div>

            <div className="mt-2 rounded-xl border border-rock-blue/15 bg-kilamanjaro/35 p-3 shadow-[inset_0_1px_0_rgba(240,237,232,0.06)]">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1 text-xs font-mono text-pampas/75">
                  <span className="text-pampas/45">$ </span>
                  <span className="break-words">{installCommand}</span>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0 border border-rock-blue/15 bg-pampas/6 hover:bg-pampas/10"
                  onClick={copyInstall}
                  aria-label="Copy install command"
                >
                  <Copy className="h-4 w-4 text-pampas/80" />
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </div>
    </Card>
  )
}
