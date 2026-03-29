"use client"

import * as React from "react"
import { Button } from "@/components/ui/button"
import { CodeBlock } from "@/components/CodeBlock"
import { OpenInIdeButtons } from "@/components/OpenInIdeButtons"
import {
  DEFAULT_AGENT_USE_CASES,
  exampleInvokeCurl,
  exampleLocalRunCommand,
  type AgentIdeContextInput,
} from "@/lib/agent-ide-context"
import { sanitizePromptForDisplay, UploadAgentDraft, ToolBundle } from "@/lib/agent-upload"

interface ReviewStepProps {
  flow: "build" | "github"
  draft: UploadAgentDraft
  selectedBundle?: ToolBundle
  selectedTools: string[]
  extractedTools?: { name: string; tool_type: string; source_path?: string }[]
  repoUrl?: string
  repoSummary?: string
  reviewNotes: string[]
  onSubmit: () => void
  isSubmitting: boolean
  submitLabel: string
}

export function ReviewStep({
  flow,
  draft,
  selectedBundle,
  selectedTools,
  extractedTools,
  repoUrl,
  repoSummary,
  reviewNotes,
  onSubmit,
  isSubmitting,
  submitLabel,
}: ReviewStepProps) {
  const [installOs, setInstallOs] = React.useState<"mac_linux" | "windows">("mac_linux")
  const reviewExampleInput = {
    question: "Summarize the main API surface and common usage patterns in this repository",
  }
  const localRun = exampleLocalRunCommand(draft.id.trim() || "your-agent-id", installOs)
  const curlExample = exampleInvokeCurl(draft.id.trim() || "your-agent-id", reviewExampleInput)
  const ideContext = React.useMemo(
    (): AgentIdeContextInput => ({
      prompt: draft.prompt,
      agentId: draft.id,
      version: draft.version,
      description: draft.description,
      useCases: DEFAULT_AGENT_USE_CASES,
      sourceRepo: repoUrl?.trim() || undefined,
    }),
    [draft.description, draft.id, draft.prompt, draft.version, repoUrl]
  )

  return (
    <div className="grid gap-5">
      <section className="rounded-[28px] border border-rock-blue/16 bg-pampas/[0.045] p-6">
        <h2 className="font-headline text-3xl text-pampas">Review before registration</h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-pampas/62">
          This page pulls the final draft, bundle, and additional tool state together before saving the agent spec.
        </p>
      </section>

      {flow === "github" && (
        <section className="rounded-[28px] border border-rock-blue/16 bg-kilamanjaro/42 p-5">
          <p className="text-xs uppercase tracking-[0.18em] text-pampas/45">Repository source</p>
          <p className="mt-2 text-sm text-pampas">{repoUrl || "Repository URL not captured"}</p>
          {repoSummary && <p className="mt-3 text-sm text-pampas/58">{repoSummary}</p>}
        </section>
      )}

      <div className="grid gap-5 xl:grid-cols-2">
        <section className="rounded-[28px] border border-rock-blue/16 bg-kilamanjaro/42 p-5">
          <p className="text-xs uppercase tracking-[0.18em] text-pampas/45">Agent details</p>
          <div className="mt-4 grid gap-3 text-sm text-pampas/78">
            <div><span className="text-pampas/48">Name:</span> {draft.name}</div>
            <div><span className="text-pampas/48">Agent ID:</span> {draft.id}</div>
            <div><span className="text-pampas/48">Version:</span> {draft.version}</div>
            <div><span className="text-pampas/48">Primitive:</span> {draft.primitive}</div>
            <div><span className="text-pampas/48">Created by:</span> {draft.credits.name || "Unknown"}</div>
            <div><span className="text-pampas/48">Tags:</span> {draft.tags.join(", ") || "None"}</div>
          </div>
          <p className="mt-5 text-sm leading-relaxed text-pampas/62">{draft.description || "No description yet."}</p>
        </section>

        <section className="rounded-[28px] border border-rock-blue/16 bg-kilamanjaro/42 p-5">
          <p className="text-xs uppercase tracking-[0.18em] text-pampas/45">Tool configuration</p>
          <div className="mt-4 grid gap-3 text-sm text-pampas/78">
            <div><span className="text-pampas/48">Selected bundle:</span> {selectedBundle?.title || selectedBundle?.bundle_id || "None"}</div>
            <div><span className="text-pampas/48">Bundle tools:</span> {(selectedBundle?.tools ?? []).join(", ") || "None"}</div>
            <div><span className="text-pampas/48">Additional tools:</span> {selectedTools.join(", ") || "None"}</div>
            <div><span className="text-pampas/48">Memory:</span> {draft.supports_memory ? `${draft.memory_policy?.mode || "last_n"} • ${draft.memory_policy?.max_messages || 10} messages` : "Disabled"}</div>
          </div>
        </section>
      </div>

      {flow === "github" && extractedTools && extractedTools.length > 0 && (
        <section className="rounded-[28px] border border-rock-blue/16 bg-kilamanjaro/42 p-5">
          <p className="text-xs uppercase tracking-[0.18em] text-pampas/45">Extracted tools (repo)</p>
          <div className="mt-4 grid gap-2 text-sm text-pampas/70">
            {extractedTools.map((tool) => (
              <div key={`${tool.name}-${tool.source_path || ""}`} className="rounded-2xl border border-rock-blue/14 bg-kilamanjaro/35 px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-pampas">{tool.name}</span>
                  <span className="text-xs text-pampas/45">{tool.tool_type}</span>
                </div>
                {tool.source_path && <div className="mt-1 text-xs text-pampas/45">{tool.source_path}</div>}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-[28px] border border-rock-blue/16 bg-kilamanjaro/42 p-5">
        <p className="text-xs uppercase tracking-[0.18em] text-pampas/45">Prompt and advanced summary</p>
        <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-pampas/66">
          {sanitizePromptForDisplay(draft.prompt) || "No prompt yet."}
        </p>
        <div className="mt-5 grid gap-3 text-sm text-pampas/54 md:grid-cols-2">
          <div>Input schema keys: {Object.keys(draft.input_schema || {}).join(", ") || "None"}</div>
          <div>Output schema keys: {Object.keys(draft.output_schema || {}).join(", ") || "None"}</div>
        </div>
      </section>

      {reviewNotes.length > 0 && (
        <section className="rounded-[28px] border border-rock-blue/16 bg-kilamanjaro/42 p-5">
          <p className="text-xs uppercase tracking-[0.18em] text-pampas/45">Review notes</p>
          <div className="mt-4 grid gap-2">
            {reviewNotes.map((note) => (
              <p key={note} className="text-sm text-pampas/62">{note}</p>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-[28px] border border-rock-blue/16 bg-kilamanjaro/42 p-5">
        <p className="text-xs uppercase tracking-[0.18em] text-pampas/45">Local run, API, and IDE</p>
        <p className="mt-2 max-w-2xl text-sm text-pampas/58">
          Same commands as the marketplace detail view. Open this agent&apos;s full context in Cursor or Claude while you finish review.
        </p>
        <div className="mt-4 inline-flex rounded-lg border border-rock-blue/30 bg-pampas/5 p-1">
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
        <div className="mt-4 space-y-3">
          <div>
            <p className="text-xs font-medium text-pampas/55 mb-1.5">Run command</p>
            <CodeBlock code={localRun} />
          </div>
          <div>
            <p className="text-xs font-medium text-pampas/55 mb-1.5">Example API request (curl)</p>
            <CodeBlock code={curlExample} />
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-xs text-pampas/50">Prefill your IDE or Claude with prompt + registry context</span>
            <OpenInIdeButtons ideContext={ideContext} variant="outline" size="sm" />
          </div>
        </div>
      </section>

      <div className="flex justify-end">
        <Button onClick={onSubmit} disabled={isSubmitting}>
          {isSubmitting ? "Saving..." : submitLabel}
        </Button>
      </div>
    </div>
  )
}
