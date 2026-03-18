"use client"

import * as React from "react"
import { ChevronDown, ChevronUp, Sparkles } from "lucide-react"
import { Input } from "@/components/ui/input"
import { UploadAgentDraft } from "@/lib/agent-upload"
import { cn } from "@/lib/utils"

interface DetailsStepProps {
  draft: UploadAgentDraft
  onChange: (draft: UploadAgentDraft) => void
  mode: "build" | "github"
  helperText?: string
}

function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(
        "min-h-[132px] w-full rounded-2xl border border-rock-blue/15 bg-kilamanjaro/55 px-4 py-3 text-sm text-pampas placeholder:text-pampas/42 shadow-[inset_0_1px_0_rgba(240,237,232,0.06)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-bayoux focus-visible:ring-offset-2 focus-visible:ring-offset-kilamanjaro",
        props.className
      )}
    />
  )
}

function Field({
  label,
  children,
  required,
  hint,
}: {
  label: string
  children: React.ReactNode
  required?: boolean
  hint?: string
}) {
  return (
    <label className="grid gap-2">
      <span className="text-sm text-pampas/75">
        {label}
        {required && <span className="ml-1 text-pampas/45">*</span>}
      </span>
      {children}
      {hint && <span className="text-xs text-pampas/45">{hint}</span>}
    </label>
  )
}

export function DetailsStep({ draft, onChange, mode, helperText }: DetailsStepProps) {
  const [advancedOpen, setAdvancedOpen] = React.useState(false)
  const [tagsText, setTagsText] = React.useState(draft.tags.join(", "))
  const [inputSchemaText, setInputSchemaText] = React.useState(JSON.stringify(draft.input_schema, null, 2))
  const [outputSchemaText, setOutputSchemaText] = React.useState(JSON.stringify(draft.output_schema, null, 2))
  const [schemaError, setSchemaError] = React.useState("")

  React.useEffect(() => {
    setTagsText(draft.tags.join(", "))
  }, [draft.tags])

  React.useEffect(() => {
    setInputSchemaText(JSON.stringify(draft.input_schema, null, 2))
  }, [draft.input_schema])

  React.useEffect(() => {
    setOutputSchemaText(JSON.stringify(draft.output_schema, null, 2))
  }, [draft.output_schema])

  const updateDraft = (partial: Partial<UploadAgentDraft>) => {
    onChange({ ...draft, ...partial })
  }

  const commitSchemaChange = (kind: "input" | "output", value: string) => {
    if (!value.trim()) {
      setSchemaError("")
      updateDraft(kind === "input" ? { input_schema: {} } : { output_schema: {} })
      return
    }

    try {
      const parsed = JSON.parse(value)
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Schema must be a JSON object")
      }
      setSchemaError("")
      updateDraft(kind === "input" ? { input_schema: parsed } : { output_schema: parsed })
    } catch (error) {
      setSchemaError(error instanceof Error ? error.message : "Schema must be valid JSON")
    }
  }

  return (
    <div className="grid gap-6">
      <div className="rounded-[28px] border border-rock-blue/16 bg-pampas/[0.045] p-6 shadow-[0_36px_90px_-70px_rgba(171,172,90,0.3)]">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-rock-blue/15 bg-kilamanjaro/35 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-pampas/62">
              <Sparkles className="h-3.5 w-3.5" />
              {mode === "build" ? "Build Flow" : "Parsed Draft"}
            </div>
            <h2 className="font-headline text-3xl text-pampas">Shape the agent details</h2>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-pampas/66">
              Keep the main path light. Advanced schemas and memory settings stay tucked away until you need them.
            </p>
          </div>
          {helperText && <p className="max-w-sm text-sm text-pampas/48">{helperText}</p>}
        </div>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <Field label="Name" required>
          <Input value={draft.name} onChange={(event) => updateDraft({ name: event.target.value })} placeholder="Concise product name" />
        </Field>
        <Field label="Agent ID" required hint="Lowercase letters, numbers, underscores, and hyphens only.">
          <Input value={draft.id} onChange={(event) => updateDraft({ id: event.target.value })} placeholder="agent-id" />
        </Field>
        <Field label="Version" required>
          <Input value={draft.version} onChange={(event) => updateDraft({ version: event.target.value })} placeholder="0.1.0" />
        </Field>
        <Field label="Primitive" required>
          <select
            value={draft.primitive}
            onChange={(event) => updateDraft({ primitive: event.target.value as UploadAgentDraft["primitive"] })}
            className="flex h-11 w-full rounded-xl border border-rock-blue/15 bg-kilamanjaro/55 px-4 py-2 text-sm text-pampas shadow-[inset_0_1px_0_rgba(240,237,232,0.06)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-bayoux focus-visible:ring-offset-2 focus-visible:ring-offset-kilamanjaro"
          >
            <option value="transform">transform</option>
            <option value="extract">extract</option>
            <option value="classify">classify</option>
          </select>
        </Field>
      </div>

      <Field label="Description" required>
        <Textarea value={draft.description} onChange={(event) => updateDraft({ description: event.target.value })} placeholder="What this agent does, who it is for, and how it should feel in the marketplace." />
      </Field>

      <div className="grid gap-5 md:grid-cols-2">
        <Field label="Tags">
          <Input
            value={tagsText}
            onChange={(event) => {
              const value = event.target.value
              setTagsText(value)
              updateDraft({
                tags: value
                  .split(",")
                  .map((tag) => tag.trim())
                  .filter(Boolean),
              })
            }}
            placeholder="research, github, support"
          />
        </Field>
        <Field label="Created by" required>
          <Input
            value={draft.credits.name}
            onChange={(event) => updateDraft({ credits: { ...draft.credits, name: event.target.value } })}
            placeholder="Your name or studio"
          />
        </Field>
      </div>

      <Field label="Profile link">
        <Input
          value={draft.credits.url || ""}
          onChange={(event) => updateDraft({ credits: { ...draft.credits, url: event.target.value } })}
          placeholder="https://..."
        />
      </Field>

      <Field label="Prompt" required>
        <Textarea value={draft.prompt} onChange={(event) => updateDraft({ prompt: event.target.value })} placeholder="Describe the agent behavior, constraints, and output style." className="min-h-[220px]" />
      </Field>

      <div className="rounded-[28px] border border-rock-blue/16 bg-kilamanjaro/42 p-5">
        <button
          type="button"
          onClick={() => setAdvancedOpen((value) => !value)}
          className="flex w-full items-center justify-between text-left"
        >
          <div>
            <p className="text-sm font-semibold text-pampas">Advanced settings</p>
            <p className="mt-1 text-sm text-pampas/52">Schemas and memory controls live here so the main path stays lighter.</p>
          </div>
          {advancedOpen ? <ChevronUp className="h-5 w-5 text-pampas/60" /> : <ChevronDown className="h-5 w-5 text-pampas/60" />}
        </button>

        {advancedOpen && (
          <div className="mt-5 grid gap-5">
            <div className="grid gap-5 md:grid-cols-2">
              <Field label="Input schema">
                <Textarea
                  value={inputSchemaText}
                  onChange={(event) => setInputSchemaText(event.target.value)}
                  onBlur={(event) => commitSchemaChange("input", event.target.value)}
                  className="min-h-[200px] font-mono text-xs"
                />
              </Field>
              <Field label="Output schema">
                <Textarea
                  value={outputSchemaText}
                  onChange={(event) => setOutputSchemaText(event.target.value)}
                  onBlur={(event) => commitSchemaChange("output", event.target.value)}
                  className="min-h-[200px] font-mono text-xs"
                />
              </Field>
            </div>

            <div className="rounded-2xl border border-rock-blue/14 bg-pampas/[0.04] p-4">
              <label className="flex items-center gap-3 text-sm text-pampas/78">
                <input
                  type="checkbox"
                  checked={draft.supports_memory}
                  onChange={(event) => updateDraft({ supports_memory: event.target.checked })}
                  className="h-4 w-4 rounded border-rock-blue/30 bg-transparent"
                />
                Enable memory settings
              </label>

              {draft.supports_memory && (
                <div className="mt-4 grid gap-4 md:grid-cols-3">
                  <Field label="Mode">
                    <Input
                      value={draft.memory_policy?.mode || "last_n"}
                      onChange={(event) =>
                        updateDraft({
                          memory_policy: {
                            mode: event.target.value,
                            max_messages: draft.memory_policy?.max_messages || 10,
                            max_chars: draft.memory_policy?.max_chars || 8000,
                          },
                        })
                      }
                    />
                  </Field>
                  <Field label="Max messages">
                    <Input
                      type="number"
                      value={draft.memory_policy?.max_messages || 10}
                      onChange={(event) =>
                        updateDraft({
                          memory_policy: {
                            mode: draft.memory_policy?.mode || "last_n",
                            max_messages: Number(event.target.value || 10),
                            max_chars: draft.memory_policy?.max_chars || 8000,
                          },
                        })
                      }
                    />
                  </Field>
                  <Field label="Max chars">
                    <Input
                      type="number"
                      value={draft.memory_policy?.max_chars || 8000}
                      onChange={(event) =>
                        updateDraft({
                          memory_policy: {
                            mode: draft.memory_policy?.mode || "last_n",
                            max_messages: draft.memory_policy?.max_messages || 10,
                            max_chars: Number(event.target.value || 8000),
                          },
                        })
                      }
                    />
                  </Field>
                </div>
              )}
            </div>

            {schemaError && <p className="text-sm text-red-300">{schemaError}</p>}
          </div>
        )}
      </div>
    </div>
  )
}
