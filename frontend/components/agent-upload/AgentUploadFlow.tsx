"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { ArrowLeft } from "lucide-react"
import { SignInButton, SignedIn, SignedOut, UserButton, useAuth, useUser } from "@clerk/nextjs"
import { Button } from "@/components/ui/button"
import { SourceSelectionStep } from "./SourceSelectionStep"
import { UploadFlowStepper } from "./UploadFlowStepper"
import { GithubImportStep } from "./GithubImportStep"
import { DetailsStep } from "./DetailsStep"
import { ToolsStep } from "./ToolsStep"
import { AddToolsModal } from "./AddToolsModal"
import { ReviewStep } from "./ReviewStep"
import { clearUploadDraftState, loadUploadDraftState, saveUploadDraftState } from "@/lib/upload-draft-persistence"
import {
  CatalogToolCategory,
  createEmptyDraft,
  fetchCatalogBundles,
  fetchCatalogTools,
  draftToRecommendToolsInput,
  fetchRepoRunResult,
  fetchRepoRunStatus,
  normalizeDraftFromRepo,
  recommendTools,
  registerAgent,
  RepoDiscoveredTool,
  RepoWrappedTool,
  serializeDraftToSpec,
  ToolBundle,
  UploadAgentDraft,
  UploadFlowPath,
  startRepoImport,
} from "@/lib/agent-upload"

const STEP_LABELS = [
  "Choose how you want to start.",
  "Capture the core agent details.",
  "Select the right tools and bundle.",
  "Review the final spec before saving.",
]

const IMPORT_STAGES = [
  "Connecting to repository",
  "Extracting tools",
  "Parsing agent details",
  "Generating recommendations",
] as const

function normalizeToolIdCandidate(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_-]/g, "")
}

function inferExtractedToolIds(args: {
  extractedTools: RepoDiscoveredTool[]
  toolCategories: CatalogToolCategory[]
}) {
  const { extractedTools, toolCategories } = args
  const promoted = new Set<string>()
  for (const category of toolCategories) {
    for (const tool of category.tools) {
      if (tool.tool_id) promoted.add(String(tool.tool_id))
    }
  }

  const inferred: string[] = []
  for (const tool of extractedTools) {
    const raw = String(tool.name || "").trim()
    if (!raw) continue
    const candidates = [raw, normalizeToolIdCandidate(raw)]
    for (const cand of candidates) {
      if (promoted.has(cand)) {
        inferred.push(cand)
        break
      }
    }
  }
  return [...new Set(inferred)]
}

function parseRepoUrl(url: string) {
  try {
    const parsed = new URL(url)
    if (parsed.hostname !== "github.com") return null
    const parts = parsed.pathname.split("/").filter(Boolean)
    if (parts.length < 2) return null
    return { owner: parts[0], repo: parts[1].replace(/\.git$/, "") }
  } catch {
    return null
  }
}

function validateDraft(draft: UploadAgentDraft) {
  const missing: string[] = []
  if (!draft.name.trim()) missing.push("Name")
  if (!draft.id.trim()) missing.push("Agent ID")
  if (!draft.version.trim()) missing.push("Version")
  if (!draft.description.trim()) missing.push("Description")
  if (!draft.primitive.trim()) missing.push("Primitive")
  if (!draft.credits.name.trim()) missing.push("Created by")
  if (!draft.prompt.trim()) missing.push("Prompt")
  if (!draft.input_schema || typeof draft.input_schema !== "object") missing.push("Input schema")
  if (!draft.output_schema || typeof draft.output_schema !== "object") missing.push("Output schema")
  return missing
}

export function AgentUploadFlow() {
  const router = useRouter()
  const { isSignedIn, getToken } = useAuth()
  const { user } = useUser()

  const [path, setPath] = React.useState<UploadFlowPath | null>(null)
  const [step, setStep] = React.useState(0)
  const [maxReachedStep, setMaxReachedStep] = React.useState(0)
  const [draft, setDraft] = React.useState<UploadAgentDraft>(createEmptyDraft)
  const [toolCategories, setToolCategories] = React.useState<CatalogToolCategory[]>([])
  const [bundles, setBundles] = React.useState<ToolBundle[]>([])
  const [selectedBundleId, setSelectedBundleId] = React.useState("")
  const [recommendedBundleId, setRecommendedBundleId] = React.useState("")
  const [recommendedTools, setRecommendedTools] = React.useState<string[]>([])
  const [selectedTools, setSelectedTools] = React.useState<string[]>([])
  const [recommendedToolIds, setRecommendedToolIds] = React.useState<string[]>([])
  const [extractedToolIds, setExtractedToolIds] = React.useState<string[]>([])
  const [userEditedBundle, setUserEditedBundle] = React.useState(false)
  const [userEditedTools, setUserEditedTools] = React.useState(false)
  const [recommendationRationale, setRecommendationRationale] = React.useState<string | null>(null)
  const [reviewNotes, setReviewNotes] = React.useState<string[]>([])
  const [repoUrl, setRepoUrl] = React.useState("")
  const [repoSummary, setRepoSummary] = React.useState("")
  const [repoRunId, setRepoRunId] = React.useState("")
  const [importLoading, setImportLoading] = React.useState(false)
  const [importProgressIndex, setImportProgressIndex] = React.useState(0)
  const [importError, setImportError] = React.useState("")
  const [statusMessage, setStatusMessage] = React.useState("")
  const [statusTone, setStatusTone] = React.useState<"idle" | "error" | "success">("idle")
  const [submitting, setSubmitting] = React.useState(false)
  const [addToolsOpen, setAddToolsOpen] = React.useState(false)
  const [extractedTools, setExtractedTools] = React.useState<RepoDiscoveredTool[]>([])
  const [wrappedRepoTools, setWrappedRepoTools] = React.useState<RepoWrappedTool[]>([])

  React.useEffect(() => {
    const persisted = loadUploadDraftState()
    if (!persisted) return
    // Only hydrate when the flow hasn't started in this session.
    if (path !== null || step !== 0 || maxReachedStep !== 0) return
    if (persisted.path !== null) setPath(persisted.path)
    setStep(typeof persisted.step === "number" ? persisted.step : 0)
    setMaxReachedStep(typeof persisted.max_reached_step === "number" ? persisted.max_reached_step : 0)
    setRepoUrl(String(persisted.repo_url || ""))
    setRepoSummary(String(persisted.repo_summary || ""))
    if (persisted.draft && typeof persisted.draft === "object") {
      setDraft((current) => ({ ...current, ...(persisted.draft as any) }))
    }
    const selections = persisted.selections || ({} as any)
    setSelectedBundleId(String(selections.selected_bundle_id || ""))
    setSelectedTools(Array.isArray(selections.selected_tool_ids) ? selections.selected_tool_ids.filter((t: any) => typeof t === "string") : [])
    setRecommendedBundleId(String(selections.recommended_bundle_id || ""))
    setRecommendedTools(Array.isArray(selections.recommended_tool_ids) ? selections.recommended_tool_ids.filter((t: any) => typeof t === "string") : [])
    setRecommendedToolIds(Array.isArray(selections.recommended_tool_ids) ? selections.recommended_tool_ids.filter((t: any) => typeof t === "string") : [])
    setExtractedToolIds(Array.isArray(selections.extracted_tool_ids) ? selections.extracted_tool_ids.filter((t: any) => typeof t === "string") : [])
    setUserEditedBundle(Boolean(selections.user_edited_bundle))
    setUserEditedTools(Boolean(selections.user_edited_tools))
  }, [maxReachedStep, path, step])

  React.useEffect(() => {
    // Debounced persistence so refresh/navigation doesn't lose progress.
    const handle = window.setTimeout(() => {
      saveUploadDraftState({
        version: 1,
        updated_at: Date.now(),
        path,
        step,
        max_reached_step: maxReachedStep,
        repo_url: repoUrl,
        repo_summary: repoSummary,
        draft,
        selections: {
          selected_bundle_id: selectedBundleId,
          selected_tool_ids: selectedTools,
          recommended_bundle_id: recommendedBundleId,
          recommended_tool_ids: recommendedToolIds,
          extracted_tool_ids: extractedToolIds,
          user_edited_bundle: userEditedBundle,
          user_edited_tools: userEditedTools,
        },
      })
    }, 250)
    return () => window.clearTimeout(handle)
  }, [
    draft,
    extractedToolIds,
    maxReachedStep,
    path,
    recommendedBundleId,
    recommendedToolIds,
    repoSummary,
    repoUrl,
    selectedBundleId,
    selectedTools,
    step,
    userEditedBundle,
    userEditedTools,
  ])

  React.useEffect(() => {
    if (!user || draft.credits.name.trim()) return
    const fallback =
      user.username ||
      user.fullName ||
      user.primaryEmailAddress?.emailAddress?.split("@")[0] ||
      ""
    if (fallback) {
      setDraft((current) => ({
        ...current,
        credits: { ...current.credits, name: fallback },
      }))
    }
  }, [user, draft.credits.name])

  React.useEffect(() => {
    let cancelled = false
    const loadCatalog = async () => {
      try {
        const [toolResponse, bundleResponse] = await Promise.all([fetchCatalogTools(), fetchCatalogBundles()])
        if (cancelled) return
        setToolCategories(toolResponse.categories || [])
        setBundles(bundleResponse.bundles || [])
      } catch (error) {
        if (cancelled) return
        setStatusTone("error")
        setStatusMessage(error instanceof Error ? error.message : "Failed to load upload dependencies")
      }
    }
    loadCatalog()
    return () => {
      cancelled = true
    }
  }, [])

  React.useEffect(() => {
    if (!path || step < 1) return
    let cancelled = false
    const recommend = async () => {
      try {
        const input = draftToRecommendToolsInput({
          draft,
          repo_url: repoUrl || undefined,
          extracted_tool_ids: extractedToolIds.length > 0 ? extractedToolIds : undefined,
        })
        const hasEnoughSignal = Boolean(input.name || input.description || input.prompt)
        if (!hasEnoughSignal) return

        const result = await recommendTools(input)
        if (cancelled) return
        setRecommendedBundleId(result.recommended_bundle_id || "")
        setRecommendedTools(result.recommended_additional_tool_ids || [])
        setRecommendedToolIds(result.recommended_additional_tool_ids || [])
        setRecommendationRationale(result.rationale || null)

        // Seed selection only if the user has not already edited.
        if (!userEditedBundle) {
          setSelectedBundleId((current) => current || result.recommended_bundle_id || "")
        }
        if (!userEditedTools) {
          setSelectedTools((current) =>
            current.length > 0 ? current : (result.recommended_additional_tool_ids || [])
          )
        }
      } catch {
        // Non-blocking.
      }
    }
    recommend()
    return () => {
      cancelled = true
    }
  }, [
    draft.description,
    draft.name,
    draft.prompt,
    draft.primitive,
    extractedToolIds,
    path,
    repoUrl,
    step,
    userEditedBundle,
    userEditedTools,
  ])

  React.useEffect(() => {
    if (!importLoading || !repoRunId) return
    let cancelled = false

    const tick = async () => {
      try {
        await fetchRepoRunStatus(repoRunId)
        if (cancelled) return
        setImportProgressIndex((current) => Math.min(current + 1, IMPORT_STAGES.length - 1))

        const result = await fetchRepoRunResult(repoRunId)
        if (cancelled) return

        if (result.pending) {
          window.setTimeout(tick, 1200)
          return
        }

        const output = result.output
        const normalized = normalizeDraftFromRepo(output.draft_agent_spec || {})
        setDraft((current) => ({
          ...current,
          ...normalized,
          credits: {
            name: normalized.credits.name || current.credits.name,
            url: normalized.credits.url || current.credits.url,
          },
        }))
        setRepoSummary(output.repo_summary || "")
        setRecommendedBundleId(output.recommended_bundle || "")
        setSelectedBundleId(output.recommended_bundle || "")
        setRecommendedTools(output.recommended_additional_tools || [])
        setRecommendedToolIds(output.recommended_additional_tools || [])
        setSelectedTools(output.recommended_additional_tools || [])
        setExtractedToolIds([]) // best-effort mapping added later; keep stable empty default for now
        setUserEditedBundle(false)
        setUserEditedTools(false)
        setRecommendationRationale(null)
        setReviewNotes(output.review_notes || [])
        const discovered = output.discovered_repo_tools || []
        setExtractedTools(discovered)
        setExtractedToolIds(inferExtractedToolIds({ extractedTools: discovered, toolCategories }))
        setWrappedRepoTools(output.wrapped_repo_tools || [])
        setImportLoading(false)
        setImportProgressIndex(IMPORT_STAGES.length - 1)
        setStep(1)
        setMaxReachedStep(1)
      } catch (error) {
        if (cancelled) return
        setImportLoading(false)
        setImportError(error instanceof Error ? error.message : "Failed to import repository")
      }
    }

    tick()

    return () => {
      cancelled = true
    }
  }, [importLoading, repoRunId])

  const selectedBundle = bundles.find((bundle) => bundle.bundle_id === selectedBundleId)

  const resetToSourceSelection = () => {
    clearUploadDraftState()
    setPath(null)
    setStep(0)
    setMaxReachedStep(0)
    setStatusMessage("")
    setStatusTone("idle")
    setImportError("")
  }

  const choosePath = (nextPath: UploadFlowPath) => {
    setPath(nextPath)
    setStatusMessage("")
    setStatusTone("idle")
    setImportError("")
    if (nextPath === "build") {
      setDraft(createEmptyDraft())
      setSelectedBundleId("")
      setRecommendedBundleId("")
      setRecommendedTools([])
      setRecommendedToolIds([])
      setSelectedTools([])
      setExtractedToolIds([])
      setUserEditedBundle(false)
      setUserEditedTools(false)
      setRecommendationRationale(null)
      setStep(1)
      setMaxReachedStep(1)
      setRepoRunId("")
      setRepoSummary("")
      setReviewNotes([])
      setExtractedTools([])
      setWrappedRepoTools([])
    } else {
      setStep(0)
      setMaxReachedStep(0)
    }
  }

  const goToStep = (nextStep: number) => {
    setStep(nextStep)
    setMaxReachedStep((current) => Math.max(current, nextStep))
    setStatusMessage("")
    setStatusTone("idle")
  }

  const startGithubImportFlow = async () => {
    setImportError("")
    if (!repoUrl.trim()) {
      setImportError("Enter a GitHub repository URL.")
      return
    }
    if (!parseRepoUrl(repoUrl)) {
      setImportError("Use a valid GitHub repository URL like https://github.com/owner/repo.")
      return
    }
    try {
      setImportLoading(true)
      setImportProgressIndex(0)
      const response = await startRepoImport(repoUrl.trim())
      setRepoRunId(response.run_id)
    } catch (error) {
      setImportLoading(false)
      setImportError(error instanceof Error ? error.message : "Failed to start repository import")
    }
  }

  const moveFromDetails = () => {
    const missing = validateDraft(draft)
    if (missing.length > 0) {
      setStatusTone("error")
      setStatusMessage(`Complete these fields before continuing: ${missing.join(", ")}`)
      return
    }
    if (!selectedBundleId && recommendedBundleId) {
      setSelectedBundleId(recommendedBundleId)
    }
    goToStep(2)
  }

  const moveFromTools = () => {
    if (!selectedBundleId && bundles.length > 0) {
      setStatusTone("error")
      setStatusMessage("Select a bundle before continuing to review.")
      return
    }
    goToStep(3)
  }

  const submit = async () => {
    if (!isSignedIn) {
      setStatusTone("error")
      setStatusMessage("Please sign in to register an agent.")
      return
    }
    try {
      setSubmitting(true)
      setStatusMessage("")
      const token = await getToken({
        template: process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE || undefined,
      })
      if (!token) {
        throw new Error("Missing session token. Please sign in again.")
      }
      const spec = serializeDraftToSpec(draft)
      if (selectedBundleId) {
        spec.bundle_id = selectedBundleId
      }
      if (selectedTools.length > 0) {
        spec.additional_tools = selectedTools
      }
      const result = await registerAgent(spec, token)
      clearUploadDraftState()
      setStatusTone("success")
      setStatusMessage(`Registered ${result.agent_id}@${result.version}`)
      window.setTimeout(() => router.push("/"), 700)
    } catch (error) {
      setStatusTone("error")
      setStatusMessage(error instanceof Error ? error.message : "Failed to register agent")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen selection-palette">
      <main className="mx-auto max-w-6xl px-4 py-12 md:px-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link href="/" className="inline-flex items-center gap-2 text-sm text-pampas/70 hover:text-pampas">
            <ArrowLeft className="h-4 w-4" />
            Back to marketplace
          </Link>
          <div className="flex items-center gap-3">
            <SignedOut>
              <SignInButton>
                <button className="rounded-full border border-rock-blue/20 bg-pampas/8 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-pampas/75">
                  Sign in
                </button>
              </SignInButton>
            </SignedOut>
            <SignedIn>
              <UserButton afterSignOutUrl="/" />
            </SignedIn>
          </div>
        </div>

        <section className="mt-6 overflow-hidden rounded-[32px] border border-rock-blue/18 bg-pampas/[0.045] shadow-[0_40px_120px_-80px_rgba(159,178,205,0.55)] backdrop-blur">
          <div
            className="border-b border-rock-blue/12 px-6 py-8 md:px-10"
            style={{
              background:
                "radial-gradient(circle at top left, rgba(171,172,90,0.12), transparent 28%), radial-gradient(circle at top right, rgba(159,178,205,0.10), transparent 32%)",
            }}
          >
            <div className="inline-flex w-fit items-center gap-2 rounded-full border border-rock-blue/18 bg-kilamanjaro/45 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-pampas/68">
              Registry Upload
            </div>
            <h1 className="mt-4 font-headline text-4xl leading-tight text-pampas md:text-5xl">
              Build and register an agent without the giant form.
            </h1>
            <div className="mt-3 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
              <p className="max-w-2xl text-sm leading-relaxed text-pampas/66 md:text-base">
                Choose a source, shape the details, tune the tools, and review the final spec in a lighter guided flow.
              </p>
              <p className="text-sm text-pampas/46">{STEP_LABELS[step]}</p>
            </div>
          </div>

          <div className="px-6 py-8 md:px-10 md:py-10">
            {path === null && <SourceSelectionStep onSelect={choosePath} />}

            {path === "github" && step === 0 && (
              <GithubImportStep
                repoUrl={repoUrl}
                onRepoUrlChange={setRepoUrl}
                onStartImport={startGithubImportFlow}
                isLoading={importLoading}
                progressLabel={IMPORT_STAGES[importProgressIndex]}
                progressValue={Math.round(((importProgressIndex + (importLoading ? 0.4 : 1)) / IMPORT_STAGES.length) * 100)}
                error={importError}
              />
            )}

            {path !== null && step === 1 && (
              <DetailsStep
                draft={draft}
                onChange={setDraft}
                mode={path}
                helperText={path === "github" ? "Parsed fields can be edited before you continue." : "Start with the core details; the rest of the flow will adapt."}
              />
            )}

            {path !== null && step === 2 && (
              <ToolsStep
                flow={path}
                bundles={bundles}
                toolCategories={toolCategories}
                recommendedBundleId={recommendedBundleId}
                selectedBundleId={selectedBundleId}
                onSelectBundle={(bundleId) => {
                  setUserEditedBundle(true)
                  setSelectedBundleId(bundleId)
                }}
                recommendedTools={recommendedTools}
                selectedTools={selectedTools}
                onToggleTool={(toolId) => {
                  setUserEditedTools(true)
                  setSelectedTools((current) =>
                    current.includes(toolId) ? current.filter((item) => item !== toolId) : [...current, toolId]
                  )
                }}
                extractedTools={extractedTools}
                wrappedRepoTools={wrappedRepoTools}
                onOpenAddTools={() => setAddToolsOpen(true)}
              />
            )}

            {path !== null && step === 3 && (
              <ReviewStep
                flow={path}
                draft={draft}
                selectedBundle={selectedBundle}
                selectedTools={selectedTools}
                extractedTools={path === "github" ? extractedTools : undefined}
                repoUrl={repoUrl}
                repoSummary={repoSummary}
                reviewNotes={reviewNotes}
                onSubmit={submit}
                isSubmitting={submitting}
                submitLabel="Save and Register Agent"
              />
            )}

            {statusMessage && (
              <div
                className={
                  statusTone === "error"
                    ? "mt-6 rounded-2xl border border-red-400/25 bg-red-500/10 px-4 py-3 text-sm text-red-200"
                    : statusTone === "success"
                      ? "mt-6 rounded-2xl border border-olive-green/24 bg-olive-green/12 px-4 py-3 text-sm text-pampas"
                      : "mt-6 rounded-2xl border border-rock-blue/15 bg-kilamanjaro/40 px-4 py-3 text-sm text-pampas/72"
                }
              >
                {statusMessage}
              </div>
            )}

            {path !== null && (
              <>
                <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    {step > 0 ? (
                      <Button
                        variant="ghost"
                        onClick={() => {
                          if (path === "build" && step === 1) {
                            resetToSourceSelection()
                            return
                          }
                          goToStep(step - 1)
                        }}
                      >
                        Back
                      </Button>
                    ) : (
                      <Button variant="ghost" onClick={resetToSourceSelection}>
                        Change source
                      </Button>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-3">
                    {path === "github" && step === 0 && (
                      <Button variant="outline" onClick={() => setPath(null)} disabled={importLoading}>
                        Cancel import
                      </Button>
                    )}
                    {step === 1 && <Button onClick={moveFromDetails}>Continue to Tools</Button>}
                    {step === 2 && <Button onClick={moveFromTools}>Continue to Review</Button>}
                  </div>
                </div>

                <UploadFlowStepper currentStep={step} maxReachedStep={maxReachedStep} />
              </>
            )}
          </div>
        </section>
      </main>

      <AddToolsModal
        open={addToolsOpen}
        onOpenChange={setAddToolsOpen}
        categories={toolCategories}
        selectedTools={selectedTools}
        onAttach={(toolIds) => {
          setUserEditedTools(true)
          setSelectedTools((current) => [...new Set([...current, ...toolIds])])
        }}
      />
    </div>
  )
}
