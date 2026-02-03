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
import { Input } from "@/components/ui/input"
import { AgentDetail, AgentSummary } from "@/lib/agents"
import { cn } from "@/lib/utils"
import { Copy } from "lucide-react"

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:4280"

interface AgentDetailModalProps {
  agent: AgentSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onCopy?: () => void
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
}: AgentDetailModalProps) {
  const [detail, setDetail] = React.useState<AgentDetail | null>(null)
  const [detailError, setDetailError] = React.useState<string | null>(null)
  const [detailLoading, setDetailLoading] = React.useState(false)
  const [sessionId, setSessionId] = React.useState<string | null>(null)
  const [sessionError, setSessionError] = React.useState<string | null>(null)
  const [note, setNote] = React.useState("")
  const [noteStatus, setNoteStatus] = React.useState<"idle" | "loading" | "ok" | "error">("idle")

  const localRunCommand = agent ? `AGENT_PRESET=${agent.id} make run` : ""
  const dockerRunCommand = agent ? `make docker-up AGENT=${agent.id}` : ""
  const exampleCurl = agent
    ? `curl -X POST ${GATEWAY_URL}/agents/${agent.id}/invoke \\\n  -H "Content-Type: application/json" \\\n  -d '{\"input\": {}}'`
    : ""
  const inputSchema = detail?.input_schema
  const outputSchema = detail?.output_schema

  React.useEffect(() => {
    if (!open || !agent) return
    let active = true
    const load = async () => {
      setDetailLoading(true)
      setDetailError(null)
      try {
        const res = await fetch(`${GATEWAY_URL}/agents/${agent.id}`)
        const data = await res.json()
        if (!active) return
        if (res.ok) {
          setDetail(data)
        } else {
          setDetailError(data?.error?.message || `Failed (${res.status})`)
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

  const handleCreateSession = async () => {
    setSessionError(null)
    try {
      const res = await fetch(`${GATEWAY_URL}/sessions`, { method: "POST" })
      const data = await res.json()
      if (res.ok && data.session_id) {
        setSessionId(data.session_id)
      } else {
        setSessionError(data?.error?.message || `Failed (${res.status})`)
      }
    } catch (e) {
      setSessionError(e instanceof Error ? e.message : "Request failed")
    }
  }

  const handleAddNote = async () => {
    if (!sessionId || !note.trim()) return
    setNoteStatus("loading")
    try {
      const res = await fetch(`${GATEWAY_URL}/sessions/${sessionId}/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events: [{ role: "user", content: note.trim() }] }),
      })
      const data = await res.json()
      if (res.ok && data.ok) {
        setNoteStatus("ok")
        setNote("")
      } else {
        setNoteStatus("error")
      }
    } catch {
      setNoteStatus("error")
    }
  }

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
            <TabsList className="grid w-full grid-cols-5">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="install">Get set up</TabsTrigger>
              <TabsTrigger value="api">API</TabsTrigger>
              <TabsTrigger value="schema">Schema</TabsTrigger>
              <TabsTrigger value="session">Session</TabsTrigger>
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
                  If you haven&apos;t already, clone the repo and run <code className="font-mono text-pampas/85">make install</code> once. For real LLM output, set up OpenRouter (API key in <code className="font-mono text-pampas/85">.env</code>) — see Get set up on the home page.
                </p>

                <div className="space-y-4">
                  <div className="space-y-2">
                    <h3 className="text-lg font-semibold text-pampas mb-1">
                      Run this agent locally
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
                    code={JSON.stringify({} as Record<string, any>, null, 2)}
                  />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-pampas mb-2">
                    Example Output
                  </h3>
                  <CodeBlock
                    code={JSON.stringify({} as Record<string, any>, null, 2)}
                  />
                </div>
              </TabsContent>

              <TabsContent value="schema" className="space-y-4">
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

              <TabsContent value="session" className="space-y-4">
                <h3 className="text-lg font-semibold text-pampas mb-2">
                  Session memory
                </h3>
                <p className="text-sm text-pampas/75">
                  Create a session to use with <code className="font-mono text-pampas/85">/invoke</code> and optional <code className="font-mono text-pampas/85">context.session_id</code>. Gateway: <code className="font-mono text-pampas/85">{GATEWAY_URL}</code>
                </p>
                <div className="space-y-2">
                  <Button type="button" variant="outline" onClick={handleCreateSession}>
                    Create session
                  </Button>
                  {sessionError && (
                    <p className="text-sm text-red-400">{sessionError}</p>
                  )}
                  {sessionId && (
                    <div className="space-y-2 mt-2">
                      <p className="text-sm text-pampas/80">Session ID:</p>
                      <CodeBlock
                        code={sessionId}
                        onCopy={async () => {
                          await navigator.clipboard.writeText(sessionId)
                          onCopy?.()
                        }}
                      />
                      <div className="flex gap-2 items-center flex-wrap">
                        <Input
                          placeholder="Add a note (event)"
                          value={note}
                          onChange={(e) => setNote(e.target.value)}
                          className="max-w-xs"
                        />
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={handleAddNote}
                          disabled={!note.trim() || noteStatus === "loading"}
                        >
                          {noteStatus === "loading" ? "Sending…" : "Add note"}
                        </Button>
                        {noteStatus === "ok" && <span className="text-sm text-green-400">Added</span>}
                        {noteStatus === "error" && <span className="text-sm text-red-400">Failed</span>}
                      </div>
                    </div>
                  )}
                </div>
              </TabsContent>
            </ScrollArea>
          </Tabs>
        </div>

        <Separator className="my-4" />

        <div className="flex items-center justify-end gap-2">
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
      </DialogContent>
    </Dialog>
  )
}
