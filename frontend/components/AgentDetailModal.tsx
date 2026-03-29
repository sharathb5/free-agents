"use client"

import * as React from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { CodeBlock } from "@/components/CodeBlock"
import { OpenInIdeButtons } from "@/components/OpenInIdeButtons"
import { AgentDetail, AgentSummary, marketplaceCardTitle } from "@/lib/agents"

type DetailExtended = AgentDetail & {
  bundle?: string
  source_repo?: string
  promoted_tools?: Array<{ name: string; command?: string; risk_level?: string; approval?: string }>
  bundle_tools?: string[]
}
import { getClerkSessionToken } from "@/lib/agent-upload"
import { DEFAULT_AGENT_USE_CASES, type AgentIdeContextInput } from "@/lib/agent-ide-context"
import { cn } from "@/lib/utils"
import { Copy } from "lucide-react"
import Link from "next/link"
import { SignedIn, useAuth } from "@clerk/nextjs"

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:4280"

interface AgentDetailModalProps {
  agent: AgentSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onCopy?: () => void
  onArchived?: () => void
  canManage?: boolean
}

const primitiveColors: Record<string, string> = {
  transform: "bg-blue-bayoux/18 text-pampas border-rock-blue/20",
  extract: "bg-rock-blue/16 text-pampas border-rock-blue/20",
  classify: "bg-pampas/8 text-pampas border-rock-blue/20",
  structured_agent: "bg-blue-bayoux/18 text-pampas border-rock-blue/20",
}

export function AgentDetailModal({
  agent,
  open,
  onOpenChange,
  onCopy,
  onArchived,
  canManage = false,
}: AgentDetailModalProps) {
  const { getToken } = useAuth()
  const [detail, setDetail] = React.useState<AgentDetail | null>(null)
  const [detailError, setDetailError] = React.useState<string | null>(null)
  const [detailLoading, setDetailLoading] = React.useState(false)
  const [installOs, setInstallOs] = React.useState<"mac_linux" | "windows">("mac_linux")
  const [archiveStatus, setArchiveStatus] = React.useState<"idle" | "loading" | "ok" | "error">("idle")
  const [archiveMessage, setArchiveMessage] = React.useState("")
  const localRunCommand = agent
    ? installOs === "windows"
      ? `$env:AGENT_PRESET=\"${agent.id}\"\nagent-toolbox`
      : `AGENT_PRESET=${agent.id} agent-toolbox`
    : ""
  const dockerRunCommand = agent
    ? `docker run -d --name agent-toolbox -p 4280:4280 -e AGENT_PRESET=${agent.id} ghcr.io/sharathb5/agent-toolbox:latest`
    : ""
  const inputSchema = detail?.input_schema
  const outputSchema = detail?.output_schema
  const [exampleInput, setExampleInput] = React.useState<Record<string, any> | null>(null)
  const [exampleOutput, setExampleOutput] = React.useState<Record<string, any> | null>(null)
  const defaultExampleInput = { question: "Summarize the main API surface and common usage patterns in this repository" }
  const defaultExampleOutput = { answer: "The openai-agents-python SDK exposes three core primitives: Agent (defined with instructions and an optional tool list), Runner (executes agent loops via Runner.run() or Runner.run_sync()), and Tool (wraps Python functions as callable capabilities). Common patterns include single-agent task loops, multi-agent handoffs using the Handoff primitive, and structured output via output_type. Key source files: src/agents/agent.py, src/agents/run.py, examples/." }
  const effectiveInput = exampleInput ?? defaultExampleInput
  const effectiveOutput = exampleOutput ?? defaultExampleOutput
  const exampleCurl = agent
    ? `curl -X POST ${GATEWAY_URL}/agents/${agent.id}/invoke \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify({ input: effectiveInput }, null, 2)}'`
    : ""

  const ideContext = React.useMemo((): AgentIdeContextInput | null => {
    if (!agent) return null
    const prompt =
      detail == null
        ? "(Loading prompt…)"
        : typeof detail.prompt === "string" && detail.prompt.trim()
          ? detail.prompt.trim()
          : "(empty)"
    const sourceRepo =
      (detail as DetailExtended)?.source_repo ||
      agent.tags?.find((t) => t.startsWith("repo:"))?.replace("repo:", "") ||
      undefined
    return {
      prompt,
      agentId: agent.id,
      version: agent.version,
      description: agent.description,
      useCases: DEFAULT_AGENT_USE_CASES,
      sourceRepo,
    }
  }, [agent, detail])

  React.useEffect(() => {
    if (!open || !agent) return
    let active = true
    const load = async () => {
      setDetailLoading(true)
      setDetailError(null)
      try {
        const versionQ = agent.version?.trim() ? `?version=${encodeURIComponent(agent.version.trim())}` : ""
        const [detailRes, exampleRes] = await Promise.all([
          fetch(`${GATEWAY_URL}/agents/${agent.id}${versionQ}`),
          fetch(`${GATEWAY_URL}/agents/${agent.id}/examples`),
        ])
        const data = await detailRes.json()
        if (!active) return
        if (detailRes.ok) {
          setDetail(data)
        } else {
          setDetailError(data?.error?.message || `Failed (${detailRes.status})`)
        }
        if (exampleRes.ok) {
          const exampleData = await exampleRes.json()
          const example = exampleData?.example || null
          setExampleInput(example?.input || null)
          setExampleOutput(example?.output || null)
        } else {
          setExampleInput(null)
          setExampleOutput(null)
        }
      } catch (e) {
        if (!active) return
        setDetailError(e instanceof Error ? e.message : "Request failed")
      } finally {
        if (active) setDetailLoading(false)
      }
    }
    load()
    return () => {
      active = false
    }
  }, [agent?.id, agent?.version, open])

  if (!agent) return null

  const modalTitle = marketplaceCardTitle((detail ?? agent) as unknown as Record<string, unknown>)

  const handleCopyCommand = async () => {
    await navigator.clipboard.writeText(localRunCommand)
    onCopy?.()
  }

  const handleCopyCurl = async () => {
    await navigator.clipboard.writeText(exampleCurl)
    onCopy?.()
  }

  const handleCopyInputSchema = async () => {
    if (!inputSchema) return
    await navigator.clipboard.writeText(JSON.stringify(inputSchema, null, 2))
    onCopy?.()
  }

  const handleArchive = async () => {
    if (!agent) return
    setArchiveStatus("loading")
    setArchiveMessage("")
    try {
      const token = await getClerkSessionToken({ getToken })
      if (!token) {
        setArchiveStatus("error")
        setArchiveMessage("Missing session token. Please sign in again.")
        return
      }
      const res = await fetch(`${GATEWAY_URL}/agents/${agent.id}/archive`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json()
      if (res.ok && data?.ok) {
        setArchiveStatus("ok")
        setArchiveMessage("Agent archived.")
        onArchived?.()
        onOpenChange(false)
      } else {
        setArchiveStatus("error")
        setArchiveMessage(data?.error?.message || `Failed (${res.status})`)
      }
    } catch (e) {
      setArchiveStatus("error")
      setArchiveMessage(e instanceof Error ? e.message : "Request failed")
    }
  }

  const handleUnarchive = async () => {
    if (!agent) return
    setArchiveStatus("loading")
    setArchiveMessage("")
    try {
      const token = await getClerkSessionToken({ getToken })
      if (!token) {
        setArchiveStatus("error")
        setArchiveMessage("Missing session token. Please sign in again.")
        return
      }
      const res = await fetch(`${GATEWAY_URL}/agents/${agent.id}/unarchive`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json()
      if (res.ok && data?.ok) {
        setArchiveStatus("ok")
        setArchiveMessage("Agent restored.")
        onArchived?.()
        onOpenChange(false)
      } else {
        setArchiveStatus("error")
        setArchiveMessage(data?.error?.message || `Failed (${res.status})`)
      }
    } catch (e) {
      setArchiveStatus("error")
      setArchiveMessage(e instanceof Error ? e.message : "Request failed")
    }
  }

  const handleCopyOutputSchema = async () => {
    if (!outputSchema) return
    await navigator.clipboard.writeText(JSON.stringify(outputSchema, null, 2))
    onCopy?.()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2 mb-2 pr-10">
                <DialogTitle className="font-headline text-2xl md:text-3xl tracking-tight">
                  {modalTitle}
                </DialogTitle>
                <Badge
                  variant="secondary"
                  className={cn(
                    "text-xs font-medium border",
                    primitiveColors[agent.primitive] || primitiveColors.transform
                  )}
                >
                  {agent.primitive}
                </Badge>
              </div>
              <DialogDescription className="text-base text-pampas/70">
                {agent.description}
              </DialogDescription>
            </div>
          </div>
          <div className="flex items-center gap-2 mt-4 flex-wrap">
            {(agent.tags || []).map((tag) => (
              <Badge
                key={tag}
                variant="outline"
                className="text-xs border-rock-blue/20 bg-pampas/6 text-pampas/75"
              >
                {tag}
              </Badge>
            ))}
          </div>
        </DialogHeader>

        <Separator className="my-4" />

        <div className="flex-1 overflow-hidden">
          <Tabs defaultValue="overview" className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="install">Run locally</TabsTrigger>
              <TabsTrigger value="api">API + Schema</TabsTrigger>
            </TabsList>

            <ScrollArea className="h-[calc(90vh-350px)] max-h-[600px] mt-4">
              <TabsContent value="overview" className="space-y-5 pr-1">
                {detailLoading && (
                  <p className="text-sm text-pampas/60">Loading details…</p>
                )}
                {detailError && (
                  <p className="text-sm text-red-400">{detailError}</p>
                )}

                {/* Purpose — always shown */}
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-pampas/40 mb-1.5">Purpose</p>
                  <p className="text-sm text-pampas/80">{agent.description}</p>
                </div>

                {/* Source — always shown */}
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-pampas/40 mb-1.5">Source</p>
                  <code className="text-sm text-pampas/80 font-mono">
                    {(detail as DetailExtended)?.source_repo ||
                      agent.tags?.find(t => t.startsWith("repo:"))?.replace("repo:", "") ||
                      "Generated from repository analysis"}
                  </code>
                </div>

                {/* Bundle — always shown */}
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-pampas/40 mb-1.5">Bundle</p>
                  <Badge variant="outline" className="text-xs border-rock-blue/20 bg-pampas/6 text-pampas/75">
                    {(detail as DetailExtended)?.bundle ?? "Repo to Agent"}
                  </Badge>
                </div>

                {/* Tools — always shown */}
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-pampas/40 mb-2">Tools</p>
                  {(detail as DetailExtended)?.bundle_tools?.length || (detail as DetailExtended)?.promoted_tools?.length ? (
                    <div className="space-y-3">
                      {(detail as DetailExtended).bundle_tools?.length ? (
                        <div>
                          <p className="text-xs text-pampas/45 mb-1.5">Bundle tools</p>
                          <div className="flex flex-wrap gap-1">
                            {(detail as DetailExtended).bundle_tools!.map(t => (
                              <Badge key={t} variant="outline" className="text-xs border-rock-blue/20 bg-pampas/6 text-pampas/75 font-mono">
                                {t}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      ) : null}
                      {(detail as DetailExtended).promoted_tools?.length ? (
                        <div>
                          <p className="text-xs text-pampas/45 mb-1.5">Repo tools</p>
                          <div className="flex flex-wrap gap-1.5">
                            {(detail as DetailExtended).promoted_tools!.map(t => (
                              <div key={t.name} className="flex items-center gap-1">
                                <Badge variant="outline" className="text-xs border-rock-blue/20 bg-pampas/6 text-pampas/75 font-mono">
                                  {t.name}
                                </Badge>
                                {t.approval && (
                                  <span className={cn(
                                    "text-[10px] font-medium",
                                    t.approval === "auto" ? "text-green-400" : "text-amber-400"
                                  )}>
                                    {t.approval === "auto" ? "AUTO-SAFE" : "REVIEW"}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div>
                        <p className="text-xs text-pampas/45 mb-1.5">Bundle tools</p>
                        <div className="flex flex-wrap gap-1">
                          {["github_repo_read"].map(t => (
                            <Badge key={t} variant="outline" className="text-xs border-rock-blue/20 bg-pampas/6 text-pampas/75 font-mono">
                              {t}
                            </Badge>
                          ))}
                        </div>
                      </div>
                      <div>
                        <p className="text-xs text-pampas/45 mb-1.5">Promoted repo tools</p>
                        <div className="flex flex-wrap gap-1.5">
                          {[
                            { name: "sync", approval: "auto" },
                            { name: "format", approval: "auto" },
                            { name: "lint", approval: "auto" },
                            { name: "mypy", approval: "auto" },
                            { name: "typecheck", approval: "auto" },
                            { name: "tests", approval: "review" },
                            { name: "tests-parallel", approval: "review" },
                            { name: "coverage", approval: "auto" },
                            { name: "build-docs", approval: "auto" },
                            { name: "serve-docs", approval: "auto" },
                            { name: "run_examples", approval: "review" },
                          ].map(t => (
                            <div key={t.name} className="flex items-center gap-1">
                              <Badge variant="outline" className="text-xs border-rock-blue/20 bg-pampas/6 text-pampas/75 font-mono">
                                {t.name}
                              </Badge>
                              <span className={cn(
                                "text-[10px] font-medium",
                                t.approval === "auto" ? "text-green-400" : "text-amber-400"
                              )}>
                                {t.approval === "auto" ? "AUTO-SAFE" : "REVIEW"}
                              </span>
                            </div>
                          ))}
                        </div>
                        <p className="text-xs text-pampas/40 mt-2">Mix of auto-safe and review-gated actions</p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Memory — always shown */}
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-pampas/40 mb-2">Memory</p>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-pampas/45 text-xs">Status</span>
                      <span className="text-green-400 text-xs font-medium">Enabled</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-pampas/45 text-xs">Strategy</span>
                      <code className="text-pampas/80 text-xs font-mono">
                        {detail?.memory_policy?.strategy ?? "last_n"}
                      </code>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-pampas/45 text-xs">Max messages</span>
                      <code className="text-pampas/80 text-xs font-mono">
                        {detail?.memory_policy?.max_messages ?? 10}
                      </code>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-pampas/45 text-xs">Max chars</span>
                      <code className="text-pampas/80 text-xs font-mono">
                        {detail?.memory_policy?.max_chars ?? 8000}
                      </code>
                    </div>
                  </div>
                </div>

                {/* Example use cases — always shown */}
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-pampas/40 mb-2">Example use cases</p>
                  <ul className="space-y-1.5">
                    {[
                      "Summarize the repository architecture",
                      "Explain the API surface and common usage patterns",
                      "Identify important scripts, commands, and development workflows",
                    ].map(uc => (
                      <li key={uc} className="flex items-start gap-2 text-sm text-pampas/75">
                        <span className="text-pampas/30 mt-0.5 shrink-0">—</span>
                        <span>{uc}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </TabsContent>

              <TabsContent value="install" className="space-y-6">
                <p className="text-sm text-pampas/75">
                  First time on this machine? Go to the{" "}
                  <Link href="/" className="text-rock-blue underline hover:text-pampas">
                    home page
                  </Link>{" "}
                  and open <span className="text-pampas/85">Get set up</span> for pipx, OpenRouter, and full CLI
                  steps. Below is only what changes per agent.
                </p>

                <div className="space-y-4">
                  <div>
                    <h3 className="text-lg font-semibold text-pampas mb-2">Shell (for run command)</h3>
                    <div className="inline-flex rounded-lg border border-rock-blue/30 bg-pampas/5 p-1">
                      <button
                        type="button"
                        onClick={() => setInstallOs("mac_linux")}
                        className={`rounded-md px-3 py-1.5 text-xs ${
                          installOs === "mac_linux"
                            ? "bg-rock-blue/25 text-pampas"
                            : "text-pampas/70 hover:text-pampas"
                        }`}
                      >
                        macOS/Linux
                      </button>
                      <button
                        type="button"
                        onClick={() => setInstallOs("windows")}
                        className={`rounded-md px-3 py-1.5 text-xs ${
                          installOs === "windows"
                            ? "bg-rock-blue/25 text-pampas"
                            : "text-pampas/70 hover:text-pampas"
                        }`}
                      >
                        Windows
                      </button>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <h3 className="text-lg font-semibold text-pampas mb-1">
                      Run this agent locally ({installOs === "windows" ? "Windows" : "macOS/Linux"})
                    </h3>
                    <CodeBlock code={localRunCommand} onCopy={handleCopyCommand} />
                    <p className="text-sm text-pampas/60">
                      Gateway listens on{" "}
                      <code className="font-mono text-pampas/85">http://localhost:4280</code>.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold text-pampas/90">Docker (optional)</h4>
                    <CodeBlock
                      code={dockerRunCommand}
                      onCopy={async () => {
                        await navigator.clipboard.writeText(dockerRunCommand)
                        onCopy?.()
                      }}
                    />
                    <p className="text-xs text-pampas/65">
                      <Link
                        href="/troubleshooting"
                        className="text-rock-blue underline hover:text-pampas"
                      >
                        Troubleshooting
                      </Link>
                    </p>
                  </div>

                  <div className="space-y-3 border-t border-rock-blue/15 pt-4">
                    <p className="text-xs text-pampas/55">
                      Open this agent&apos;s prompt and registry context in Cursor or Claude right after you run it locally.
                    </p>
                    <OpenInIdeButtons ideContext={ideContext} variant="outline" />
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="api" className="space-y-5 pr-1">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-pampas/40 mb-2">Endpoint</p>
                  <div className="flex items-center gap-2 mb-2">
                    <Badge className="bg-rock-blue/20 text-rock-blue border border-rock-blue/30 text-xs font-mono">POST</Badge>
                    <code className="text-sm text-pampas/85 font-mono break-all">{GATEWAY_URL}/agents/{agent.id}/invoke</code>
                  </div>
                  <p className="text-sm text-pampas/55">
                    Runs the agent with the provided input and returns a structured response. Accepts JSON, responds with JSON.
                  </p>
                </div>

                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-pampas/40 mb-2">Example request</p>
                  <CodeBlock code={exampleCurl} onCopy={handleCopyCurl} />
                </div>

                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-pampas/40 mb-2">Example output</p>
                  <CodeBlock code={JSON.stringify(effectiveOutput, null, 2)} />
                </div>

                <Separator />

                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-pampas/40 mb-2">Input schema</p>
                  {inputSchema ? (
                    <CodeBlock code={JSON.stringify(inputSchema, null, 2)} onCopy={handleCopyInputSchema} />
                  ) : (
                    <p className="text-sm text-pampas/60">Schema unavailable.</p>
                  )}
                </div>

                <Separator />

                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-pampas/40 mb-2">Output schema</p>
                  {outputSchema ? (
                    <CodeBlock code={JSON.stringify(outputSchema, null, 2)} onCopy={handleCopyOutputSchema} />
                  ) : (
                    <p className="text-sm text-pampas/60">Schema unavailable.</p>
                  )}
                </div>
              </TabsContent>

            </ScrollArea>
          </Tabs>
        </div>

        <Separator className="my-4" />

        <div className="flex flex-wrap items-center justify-between gap-3">
          {detail?.credits && (
            <div className="text-xs text-pampas/65">
              <span className="text-pampas/45">Created by:</span>{" "}
              {detail.credits.url ? (
                <a
                  href={detail.credits.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-rock-blue underline hover:text-pampas"
                >
                  {detail.credits.name}
                </a>
              ) : (
                <span className="text-pampas/75">{detail.credits.name}</span>
              )}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <SignedIn>
              {canManage && (
                <>
                  <Link
                    href={`/upload?from_agent=${encodeURIComponent(agent.id)}&version=${encodeURIComponent(agent.version ?? "")}`}
                    className={cn(
                      "inline-flex items-center justify-center rounded-xl px-3 py-2 text-sm font-medium",
                      "border border-rock-blue/20 bg-pampas/6 text-pampas/80 hover:bg-pampas/10"
                    )}
                  >
                    Edit
                  </Link>
                  {agent.archived ? (
                    <Button
                      variant="ghost"
                      onClick={handleUnarchive}
                      disabled={archiveStatus === "loading"}
                      className="text-amber-200 hover:text-amber-100"
                    >
                      {archiveStatus === "loading" ? "Restoring..." : "Unarchive"}
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      onClick={handleArchive}
                      disabled={archiveStatus === "loading"}
                      className="text-red-300 hover:text-red-200"
                    >
                      {archiveStatus === "loading" ? "Archiving..." : "Archive"}
                    </Button>
                  )}
                </>
              )}
            </SignedIn>
          <Button
            variant="outline"
            onClick={() => {
              navigator.clipboard.writeText(exampleCurl)
              onCopy?.()
            }}
            aria-label="Copy example curl for this agent"
          >
            <Copy className="h-4 w-4 mr-2" />
            Copy API Snippet
          </Button>
          <Button
            onClick={handleCopyCommand}
            aria-label="Copy the local run command for this agent"
          >
            <Copy className="h-4 w-4 mr-2" />
            Copy run command
          </Button>
          <OpenInIdeButtons ideContext={ideContext} variant="outline" />
          </div>
        </div>
        {archiveMessage && (
          <p
            className={cn(
              "text-xs",
              archiveStatus === "ok" ? "text-green-300" : "text-red-400"
            )}
          >
            {archiveMessage}
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}
