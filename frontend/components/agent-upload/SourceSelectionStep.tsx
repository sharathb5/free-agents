"use client"

import { ArrowRight, Github, Sparkles } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"

interface SourceSelectionStepProps {
  onSelect: (path: "build" | "github") => void
}

const options = [
  {
    id: "build" as const,
    title: "Build an Agent",
    subtitle: "Start from scratch by describing your agent and configuring it step by step",
    icon: Sparkles,
    accent: "rgba(171,172,90,0.28)",
  },
  {
    id: "github" as const,
    title: "Upload from GitHub",
    subtitle: "Import a repository, parse agent/tool details, and continue setup",
    icon: Github,
    accent: "rgba(159,178,205,0.26)",
  },
]

export function SourceSelectionStep({ onSelect }: SourceSelectionStepProps) {
  return (
    <div className="grid gap-5 md:grid-cols-2">
      {options.map((option) => {
        const Icon = option.icon
        return (
          <button
            key={option.id}
            type="button"
            onClick={() => onSelect(option.id)}
            className="text-left"
          >
            <Card
              className="group relative h-full overflow-hidden rounded-[28px] border-rock-blue/16 bg-pampas/[0.045] transition duration-300 hover:border-rock-blue/28 hover:bg-pampas/[0.07]"
              style={{
                boxShadow: `0 36px 90px -62px ${option.accent}`,
              }}
            >
              <div
                className="pointer-events-none absolute inset-0 opacity-70"
                style={{
                  background: `radial-gradient(circle at top left, ${option.accent}, transparent 55%)`,
                }}
              />
              <CardHeader className="relative pb-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-rock-blue/18 bg-kilamanjaro/35 text-pampas shadow-[inset_0_1px_0_rgba(240,237,232,0.06)]">
                  <Icon className="h-5 w-5" />
                </div>
                <CardTitle className="font-headline text-3xl">{option.title}</CardTitle>
                <CardDescription className="max-w-sm text-base leading-relaxed text-pampas/68">
                  {option.subtitle}
                </CardDescription>
              </CardHeader>
              <CardContent className="relative pt-0">
                <div className="flex items-center justify-between rounded-2xl border border-rock-blue/14 bg-kilamanjaro/35 px-4 py-3 text-sm text-pampas/70">
                  <span>{option.id === "build" ? "Guided setup flow" : "Repository import and parsing"}</span>
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                </div>
              </CardContent>
            </Card>
          </button>
        )
      })}
    </div>
  )
}
