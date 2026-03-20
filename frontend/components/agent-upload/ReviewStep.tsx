"use client"

import { Button } from "@/components/ui/button"
import { UploadAgentDraft, ToolBundle } from "@/lib/agent-upload"

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
            <div><span className="text-pampas/48">Bundle tools:</span> {selectedBundle?.tools.join(", ") || "None"}</div>
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
        <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-pampas/66">{draft.prompt || "No prompt yet."}</p>
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

      <div className="flex justify-end">
        <Button onClick={onSubmit} disabled={isSubmitting}>
          {isSubmitting ? "Saving..." : submitLabel}
        </Button>
      </div>
    </div>
  )
}
