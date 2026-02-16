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
import { AgentDetail, AgentSummary } from "@/lib/agents"
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
  const exampleCurl = agent
    ? `# Agent: ${agent.name}\ncurl -X POST ${GATEWAY_URL}/agents/${agent.id}/invoke \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify({ input: exampleInput ?? {} })}'`
    : ""

  React.useEffect(() => {
    if (!open || !agent) return
    let active = true
    const load = async () => {
      setDetailLoading(true)
      setDetailError(null)
      try {
        const [detailRes, exampleRes] = await Promise.all([
          fetch(`${GATEWAY_URL}/agents/${agent.id}`),
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
  }, [agent?.id, open])

  if (!agent) return null

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
      const token = await getToken({
        template: process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE || undefined,
      })
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
      const token = await getToken({
        template: process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE || undefined,
      })
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
                  {agent.name}
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
              <TabsTrigger value="install">Get set up</TabsTrigger>
              <TabsTrigger value="api">API + Schema</TabsTrigger>
            </TabsList>

            <ScrollArea className="h-[calc(90vh-350px)] max-h-[600px] mt-4">
              <TabsContent value="overview" className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold text-pampas mb-2">
                    Description
                  </h3>
                  <p className="text-pampas/75">{agent.description}</p>
                </div>
                {detailLoading && (
                  <p className="text-sm text-pampas/60">Loading details…</p>
                )}
                {detailError && (
                  <p className="text-sm text-red-400">{detailError}</p>
                )}
              </TabsContent>

              <TabsContent value="install" className="space-y-6">
                <p className="text-sm text-pampas/75">
                  Install via pipx and run the preset locally. For real LLM output, set up OpenRouter (API key in{" "}
                  <code className="font-mono text-pampas/85">.env</code>) — see Get set up on the home page.
                </p>

                <div className="space-y-4">
                  <div>
                    <h3 className="text-lg font-semibold text-pampas mb-2">Choose your OS</h3>
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
                      Install (once)
                    </h3>
                    <CodeBlock
                      code={`pipx install agent-toolbox\nagent-toolbox setup`}
                    />
                    <p className="text-sm text-pampas/60">
                      If this fails, use the troubleshooting guide for OS-specific setup.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <h3 className="text-lg font-semibold text-pampas mb-1">
                      Run this agent locally ({installOs === "windows" ? "Windows" : "macOS/Linux"})
                    </h3>
                    <CodeBlock code={localRunCommand} onCopy={handleCopyCommand} />
                    <p className="text-sm text-pampas/60">
                      Starts the gateway for this preset on{" "}
                      <code className="font-mono text-pampas/85">http://localhost:4280</code>.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold text-pampas/90">
                      Run with Docker (alternative)
                    </h4>
                    <CodeBlock
                      code={dockerRunCommand}
                      onCopy={async () => {
                        await navigator.clipboard.writeText(dockerRunCommand)
                        onCopy?.()
                      }}
                    />
                    <p className="text-sm text-pampas/60">
                      Runs the gateway for this preset via Docker on{" "}
                      <code className="font-mono text-pampas/85">http://localhost:4280</code>.
                    </p>
                    <p className="text-xs text-pampas/60">
                      Session memory is available via CLI calls (
                      <code className="font-mono text-pampas/85">POST /sessions</code> and{" "}
                      <code className="font-mono text-pampas/85">POST /sessions/&lt;id&gt;/events</code>)
                      when you need it.
                    </p>
                    <div className="mt-2 space-y-2">
                      <CodeBlock code={`curl -X POST ${GATEWAY_URL}/sessions`} />
                      <CodeBlock
                        code={`curl -X POST ${GATEWAY_URL}/sessions/<id>/events \\\n  -H "Content-Type: application/json" \\\n  -d '{\"events\": [{\"role\": \"user\", \"content\": \"Remember this note\"}]}'`}
                      />
                    </div>
                    <p className="text-xs text-pampas/65 mt-2">
                      Having issues?{" "}
                      <Link
                        href="/troubleshooting"
                        className="text-rock-blue underline hover:text-pampas"
                      >
                        Open troubleshooting
                      </Link>
                      .
                    </p>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="api" className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold text-pampas mb-2">
                    Invoke Endpoint
                  </h3>
                  <CodeBlock code={exampleCurl} onCopy={handleCopyCurl} />
                </div>
                <Separator />
                <div>
                  <h3 className="text-lg font-semibold text-pampas mb-2">
                    Example Input
                  </h3>
                  <CodeBlock
                    code={JSON.stringify(exampleInput || {}, null, 2)}
                  />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-pampas mb-2">
                    Example Output
                  </h3>
                  <CodeBlock
                    code={JSON.stringify(exampleOutput || {}, null, 2)}
                  />
                </div>
                <Separator />
                <div>
                  <h3 className="text-lg font-semibold text-pampas mb-2">
                    Input Schema
                  </h3>
                  <div className="relative">
                    {inputSchema ? (
                      <CodeBlock
                        code={JSON.stringify(inputSchema, null, 2)}
                        onCopy={handleCopyInputSchema}
                      />
                    ) : (
                      <p className="text-sm text-pampas/60">Schema unavailable.</p>
                    )}
                  </div>
                </div>
                <Separator />
                <div>
                  <h3 className="text-lg font-semibold text-pampas mb-2">
                    Output Schema
                  </h3>
                  <div className="relative">
                    {outputSchema ? (
                      <CodeBlock
                        code={JSON.stringify(outputSchema, null, 2)}
                        onCopy={handleCopyOutputSchema}
                      />
                    ) : (
                      <p className="text-sm text-pampas/60">Schema unavailable.</p>
                    )}
                  </div>
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
                    href={`/upload?edit=1&id=${encodeURIComponent(agent.id)}`}
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
