"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { ArrowLeft, UploadCloud } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:4280"

export default function UploadAgentPage() {
  const router = useRouter()
  const [agentId, setAgentId] = React.useState("")
  const [version, setVersion] = React.useState("")
  const [name, setName] = React.useState("")
  const [description, setDescription] = React.useState("")
  const [primitive, setPrimitive] = React.useState("transform")
  const [tags, setTags] = React.useState("")
  const [prompt, setPrompt] = React.useState("")
  const [inputSchema, setInputSchema] = React.useState("")
  const [outputSchema, setOutputSchema] = React.useState("")
  const [supportsMemory, setSupportsMemory] = React.useState(false)
  const [memoryMode, setMemoryMode] = React.useState("last_n")
  const [memoryMaxMessages, setMemoryMaxMessages] = React.useState("10")
  const [memoryMaxChars, setMemoryMaxChars] = React.useState("8000")
  const [status, setStatus] = React.useState<"idle" | "loading" | "ok" | "error">("idle")
  const [statusMessage, setStatusMessage] = React.useState("")
  const [fieldErrors, setFieldErrors] = React.useState<string[]>([])

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setStatus("loading")
    setStatusMessage("")
    setFieldErrors([])

    const missing: string[] = []
    if (!agentId.trim()) missing.push("Agent ID")
    if (!version.trim()) missing.push("Version")
    if (!name.trim()) missing.push("Name")
    if (!description.trim()) missing.push("Description")
    if (!primitive.trim()) missing.push("Primitive")
    if (!prompt.trim()) missing.push("Prompt")
    if (!inputSchema.trim()) missing.push("Input schema")
    if (!outputSchema.trim()) missing.push("Output schema")
    if (missing.length > 0) {
      setStatus("error")
      setFieldErrors(missing)
      setStatusMessage("Please fill all required fields.")
      return
    }

    let parsedInputSchema: unknown
    let parsedOutputSchema: unknown
    try {
      parsedInputSchema = JSON.parse(inputSchema || "{}")
      parsedOutputSchema = JSON.parse(outputSchema || "{}")
    } catch (err) {
      setStatus("error")
      setStatusMessage("Input/Output schema must be valid JSON.")
      return
    }

    const tagsList = tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)

    const spec: Record<string, unknown> = {
      id: agentId.trim(),
      version: version.trim(),
      name: name.trim(),
      description: description.trim(),
      primitive,
      prompt: prompt.trim(),
      input_schema: parsedInputSchema,
      output_schema: parsedOutputSchema,
      supports_memory: supportsMemory,
    }

    if (tagsList.length > 0) {
      spec.tags = tagsList
    }
    if (supportsMemory) {
      spec.memory_policy = {
        mode: memoryMode.trim() || "last_n",
        max_messages: Number(memoryMaxMessages || 10),
        max_chars: Number(memoryMaxChars || 8000),
      }
    }

    try {
      const res = await fetch(`${GATEWAY_URL}/agents/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spec }),
      })
      const data = await res.json()
      if (res.ok && data?.ok) {
        setStatus("ok")
        setStatusMessage(`Registered ${data.agent_id}@${data.version}`)
        setTimeout(() => {
          router.push("/")
        }, 800)
      } else {
        setStatus("error")
        setStatusMessage(data?.error?.message || `Failed (${res.status})`)
      }
    } catch (err) {
      setStatus("error")
      setStatusMessage(err instanceof Error ? err.message : "Request failed")
    }
  }

  return (
    <div className="min-h-screen selection-palette">
      <main className="mx-auto max-w-5xl px-4 md:px-8 py-12">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-sm text-pampas/70 hover:text-pampas"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to marketplace
        </Link>

        <div className="mt-6 rounded-3xl border border-rock-blue/20 bg-pampas/6 p-6 md:p-10 shadow-[0_40px_120px_-80px_rgba(159,178,205,0.55)] backdrop-blur">
          <div className="flex flex-col gap-2">
            <div className="inline-flex w-fit items-center gap-2 rounded-full border border-rock-blue/18 bg-pampas/6 px-3 py-1 text-xs font-semibold tracking-[0.18em] text-pampas/75">
              REGISTRY UPLOAD
            </div>
            <h1 className="font-headline text-3xl md:text-4xl leading-tight text-pampas">
              Upload your own agent
            </h1>
            <p className="text-sm md:text-base text-pampas/70">
              Fill out the required fields to register an agent spec. You can paste JSON
              schemas directly into the input and output schema boxes.
            </p>
          </div>

          <form className="mt-8 grid gap-6" onSubmit={handleSubmit}>
            <section className="grid gap-4 md:grid-cols-2">
              <div className="grid gap-2">
                <label className="text-sm text-pampas/75">
                  Agent ID <span className="text-pampas/60">*</span>
                </label>
                <Input
                  placeholder="e.g. summarizer-pro"
                  value={agentId}
                  onChange={(e) => setAgentId(e.target.value)}
                  className="bg-white/5 placeholder:text-white/85 placeholder:opacity-100"
                />
              </div>
              <div className="grid gap-2">
                <label className="text-sm text-pampas/75">
                  Version <span className="text-pampas/60">*</span>
                </label>
                <Input
                  placeholder="e.g. 1.0.0"
                  value={version}
                  onChange={(e) => setVersion(e.target.value)}
                  className="bg-white/5 placeholder:text-white/85 placeholder:opacity-100"
                />
              </div>
              <div className="grid gap-2">
                <label className="text-sm text-pampas/75">
                  Name <span className="text-pampas/60">*</span>
                </label>
                <Input
                  placeholder="Human-friendly agent name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="bg-white/5 placeholder:text-white/85 placeholder:opacity-100"
                />
              </div>
              <div className="grid gap-2">
                <label className="text-sm text-pampas/75">
                  Description <span className="text-pampas/60">*</span>
                </label>
                <Input
                  placeholder="What does this agent do?"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="bg-white/5 placeholder:text-white/85 placeholder:opacity-100"
                />
              </div>
              <div className="grid gap-2">
                <label className="text-sm text-pampas/75">
                  Primitive <span className="text-pampas/60">*</span>
                </label>
                <select
                  className="h-11 rounded-xl border border-rock-blue/15 bg-white/5 px-3 text-sm text-pampas focus:border-blue-bayoux/70 focus:outline-none"
                  value={primitive}
                  onChange={(e) => setPrimitive(e.target.value)}
                >
                  <option value="transform">transform</option>
                  <option value="extract">extract</option>
                  <option value="classify">classify</option>
                </select>
              </div>
              <div className="grid gap-2">
                <label className="text-sm text-pampas/75">Tags (comma-separated)</label>
                <Input
                  placeholder="summarization, text, reports"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  className="bg-white/5 placeholder:text-white/85 placeholder:opacity-100"
                />
              </div>
            </section>
            {fieldErrors.length > 0 && (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                Missing required fields: {fieldErrors.join(", ")}.
              </div>
            )}

            <section className="grid gap-4">
              <div className="grid gap-2">
                <label className="text-sm text-pampas/75">
                  Prompt <span className="text-pampas/60">*</span>
                </label>
                <textarea
                  className="min-h-[120px] rounded-xl border border-rock-blue/15 bg-white/5 px-3 py-3 text-sm text-pampas placeholder:text-white/85 placeholder:opacity-100 focus:border-blue-bayoux/70 focus:outline-none"
                  placeholder="Describe the agent's behavior and instructions..."
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                />
              </div>
            </section>

            <section className="grid gap-4 md:grid-cols-2">
              <div className="grid gap-2">
                <label className="text-sm text-pampas/75">
                  Input Schema (JSON) <span className="text-pampas/60">*</span>
                </label>
                <textarea
                  className="min-h-[180px] rounded-xl border border-rock-blue/15 bg-white/5 px-3 py-3 text-sm font-mono text-pampas placeholder:text-white/85 placeholder:opacity-100 focus:border-blue-bayoux/70 focus:outline-none"
                  placeholder={`{\n  "type": "object",\n  "required": ["text"],\n  "properties": {\n    "text": { "type": "string" }\n  }\n}`}
                  value={inputSchema}
                  onChange={(e) => setInputSchema(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <label className="text-sm text-pampas/75">
                  Output Schema (JSON) <span className="text-pampas/60">*</span>
                </label>
                <textarea
                  className="min-h-[180px] rounded-xl border border-rock-blue/15 bg-white/5 px-3 py-3 text-sm font-mono text-pampas placeholder:text-white/85 placeholder:opacity-100 focus:border-blue-bayoux/70 focus:outline-none"
                  placeholder={`{\n  "type": "object",\n  "required": ["summary"],\n  "properties": {\n    "summary": { "type": "string" }\n  }\n}`}
                  value={outputSchema}
                  onChange={(e) => setOutputSchema(e.target.value)}
                />
              </div>
            </section>

            <section className="grid gap-4 md:grid-cols-3">
              <div className="flex items-center gap-3 rounded-xl border border-rock-blue/15 bg-pampas/6 px-4 py-3">
                <input
                  id="supports-memory"
                  type="checkbox"
                  className="relative h-4 w-4 appearance-none rounded border border-white/30 bg-black/30 checked:border-rock-blue/60 checked:bg-rock-blue/30 focus:outline-none focus:ring-2 focus:ring-rock-blue/30 checked:after:absolute checked:after:inset-[3px] checked:after:rounded-sm checked:after:bg-rock-blue/80 checked:after:content-['']"
                  checked={supportsMemory}
                  onChange={(e) => setSupportsMemory(e.target.checked)}
                />
                <label htmlFor="supports-memory" className="text-sm text-pampas/75">
                  Supports memory
                </label>
              </div>
              <div className="grid gap-2">
                <label className="text-sm text-pampas/75">Memory mode</label>
                <Input
                  placeholder="last_n"
                  value={memoryMode}
                  onChange={(e) => setMemoryMode(e.target.value)}
                  disabled={!supportsMemory}
                />
              </div>
              <div className="grid gap-2">
                <label className="text-sm text-pampas/75">Max messages</label>
                <Input
                  placeholder="10"
                  value={memoryMaxMessages}
                  onChange={(e) => setMemoryMaxMessages(e.target.value)}
                  disabled={!supportsMemory}
                />
              </div>
              <div className="grid gap-2 md:col-span-2">
                <label className="text-sm text-pampas/75">Max chars</label>
                <Input
                  placeholder="8000"
                  value={memoryMaxChars}
                  onChange={(e) => setMemoryMaxChars(e.target.value)}
                  disabled={!supportsMemory}
                />
              </div>
            </section>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-pampas/55">
                Required fields marked with <span className="text-pampas/60">*</span>.
              </p>
              <Button type="submit" className="h-11 rounded-xl" disabled={status === "loading"}>
                <UploadCloud className="mr-2 h-4 w-4" />
                {status === "loading" ? "Uploading..." : "Upload agent"}
              </Button>
            </div>
            {status !== "idle" && (
              <div
                className={[
                  "rounded-xl border px-4 py-3 text-sm",
                  status === "ok"
                    ? "border-green-500/30 bg-green-500/10 text-green-200"
                    : "border-red-500/30 bg-red-500/10 text-red-200",
                ].join(" ")}
              >
                {statusMessage || (status === "ok" ? "Agent registered." : "Upload failed.")}
              </div>
            )}
          </form>
        </div>
      </main>
    </div>
  )
}
