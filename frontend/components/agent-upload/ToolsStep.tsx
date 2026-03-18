"use client"

import { Plus, Sparkles, Wrench, Layers3, GitFork } from "lucide-react"
import { Button } from "@/components/ui/button"
import { CatalogToolCategory, RepoDiscoveredTool, RepoWrappedTool, ToolBundle } from "@/lib/agent-upload"
import { cn } from "@/lib/utils"

interface ToolsStepProps {
  flow: "build" | "github"
  bundles: ToolBundle[]
  toolCategories: CatalogToolCategory[]
  recommendedBundleId?: string
  selectedBundleId?: string
  onSelectBundle: (bundleId: string) => void
  recommendedTools: string[]
  selectedTools: string[]
  onToggleTool: (toolId: string) => void
  extractedTools: RepoDiscoveredTool[]
  wrappedRepoTools: RepoWrappedTool[]
  onOpenAddTools: () => void
}

function resolveTool(toolId: string, categories: CatalogToolCategory[]) {
  for (const category of categories) {
    const match = category.tools.find((tool) => tool.tool_id === toolId)
    if (match) return { ...match, categoryName: category.name }
  }
  return null
}

function Panel({
  title,
  description,
  icon: Icon,
  children,
}: {
  title: string
  description: string
  icon: typeof Sparkles
  children: React.ReactNode
}) {
  return (
    <section className="rounded-[28px] border border-rock-blue/16 bg-pampas/[0.045] p-5">
      <div className="mb-4 flex items-start gap-3">
        <div className="mt-1 flex h-10 w-10 items-center justify-center rounded-2xl border border-rock-blue/14 bg-kilamanjaro/38 text-pampas">
          <Icon className="h-4.5 w-4.5" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-pampas">{title}</h3>
          <p className="mt-1 text-sm text-pampas/58">{description}</p>
        </div>
      </div>
      {children}
    </section>
  )
}

export function ToolsStep({
  flow,
  bundles,
  toolCategories,
  recommendedBundleId,
  selectedBundleId,
  onSelectBundle,
  recommendedTools,
  selectedTools,
  onToggleTool,
  extractedTools,
  wrappedRepoTools,
  onOpenAddTools,
}: ToolsStepProps) {
  const selectedBundle = bundles.find((bundle) => bundle.bundle_id === selectedBundleId)
  const selectedBundleToolSet = new Set(selectedBundle?.tools || [])

  return (
    <div className="grid gap-5">
      <Panel
        title="Recommended bundle"
        description="Pick the starting tool posture for this agent. The selected bundle becomes part of the saved agent spec."
        icon={Layers3}
      >
        <div className="grid gap-3 md:grid-cols-2">
          {bundles.map((bundle) => {
            const isSuggested = bundle.bundle_id === recommendedBundleId
            const isSelected = bundle.bundle_id === selectedBundleId
            return (
              <button
                key={bundle.bundle_id}
                type="button"
                onClick={() => onSelectBundle(bundle.bundle_id)}
                className={cn(
                  "rounded-2xl border p-4 text-left transition",
                  isSelected ? "border-blue-bayoux bg-blue-bayoux/10" : "border-rock-blue/14 bg-kilamanjaro/35 hover:border-rock-blue/24"
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-pampas">{bundle.title || bundle.bundle_id}</p>
                    <p className="mt-1 text-sm text-pampas/58">{bundle.description || "No description yet."}</p>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    {isSuggested && (
                      <span className="rounded-full border border-olive-green/24 bg-olive-green/14 px-2 py-0.5 text-[11px] uppercase tracking-[0.18em] text-pampas/84">
                        Suggested
                      </span>
                    )}
                    {isSelected && (
                      <span className="rounded-full border border-blue-bayoux/24 bg-blue-bayoux/16 px-2 py-0.5 text-[11px] uppercase tracking-[0.18em] text-pampas/84">
                        Selected
                      </span>
                    )}
                  </div>
                </div>
                <p className="mt-3 text-xs text-pampas/45">Bundle tools: {(bundle.tools || []).join(", ") || "none"}</p>
              </button>
            )
          })}
        </div>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-[1.3fr_0.9fr]">
        <Panel
          title="Recommended additional tools"
          description="These are promoted tools suggested beyond the bundle. You can keep, remove, or add more."
          icon={Sparkles}
        >
          <div className="grid gap-3">
            {recommendedTools.length > 0 ? (
              recommendedTools.map((toolId) => {
                const tool = resolveTool(toolId, toolCategories)
                const selected = selectedTools.includes(toolId)
                const inBundle = selectedBundleToolSet.has(toolId)
                return (
                  <div key={toolId} className="rounded-2xl border border-rock-blue/14 bg-kilamanjaro/35 p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold text-pampas">{toolId}</p>
                          {inBundle && (
                            <span className="rounded-full border border-rock-blue/15 bg-pampas/[0.06] px-2 py-0.5 text-[11px] uppercase tracking-[0.18em] text-pampas/54">
                              In bundle
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-pampas/58">{tool?.description || "Catalog recommendation."}</p>
                      </div>
                      {!inBundle && (
                        <Button variant={selected ? "secondary" : "outline"} onClick={() => onToggleTool(toolId)}>
                          {selected ? "Remove" : "Add"}
                        </Button>
                      )}
                    </div>
                  </div>
                )
              })
            ) : (
              <div className="rounded-2xl border border-dashed border-rock-blue/14 bg-pampas/[0.03] px-4 py-10 text-center text-sm text-pampas/48">
                No additional promoted tools were recommended for this agent yet.
              </div>
            )}
          </div>
        </Panel>

        <Panel
          title="Selected tool state"
          description="This is the actual set that will be persisted alongside the selected bundle."
          icon={Wrench}
        >
          <div className="grid gap-3">
            <div className="rounded-2xl border border-rock-blue/14 bg-kilamanjaro/35 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-pampas/45">Selected bundle</p>
              <p className="mt-2 text-sm text-pampas">{selectedBundle?.title || selectedBundle?.bundle_id || "No bundle selected"}</p>
            </div>

            <div className="rounded-2xl border border-rock-blue/14 bg-kilamanjaro/35 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-pampas/45">Additional tools</p>
                  <p className="mt-2 text-sm text-pampas/58">Tools attached beyond whatever the bundle already provides.</p>
                </div>
                <Button variant="outline" onClick={onOpenAddTools}>
                  <Plus className="mr-2 h-4 w-4" />
                  Add Tools
                </Button>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {selectedTools.length > 0 ? (
                  selectedTools.map((toolId) => (
                    <button
                      type="button"
                      key={toolId}
                      onClick={() => onToggleTool(toolId)}
                      className="rounded-full border border-blue-bayoux/25 bg-blue-bayoux/12 px-3 py-1 text-sm text-pampas"
                    >
                      {toolId}
                    </button>
                  ))
                ) : (
                  <span className="text-sm text-pampas/48">No additional tools selected.</span>
                )}
              </div>
            </div>
          </div>
        </Panel>
      </div>

      {flow === "github" && (
        <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
          <Panel
            title="Extracted from repository"
            description="These came directly from repo inspection so it is obvious what the parser found."
            icon={GitFork}
          >
            <div className="grid gap-3">
              {extractedTools.length > 0 ? (
                extractedTools.map((tool) => (
                  <div key={`${tool.name}-${tool.source_path}`} className="rounded-2xl border border-rock-blue/14 bg-kilamanjaro/35 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-pampas">{tool.name}</p>
                        <p className="mt-1 text-sm text-pampas/58">{tool.description || tool.command || "Repository tool"}</p>
                        <p className="mt-2 text-xs text-pampas/42">{tool.source_path || "Source path unavailable"}</p>
                      </div>
                      <span className="rounded-full border border-rock-blue/15 bg-pampas/[0.05] px-2 py-0.5 text-[11px] uppercase tracking-[0.18em] text-pampas/52">
                        {tool.tool_type}
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed border-rock-blue/14 bg-pampas/[0.03] px-4 py-10 text-center text-sm text-pampas/48">
                  No repo tools were extracted from the import output.
                </div>
              )}
            </div>
          </Panel>

          <Panel
            title="Promoted repo tool metadata"
            description="Wrapped or promoted tool metadata is surfaced here so the boundary to future import support stays visible."
            icon={Wrench}
          >
            <div className="grid gap-3">
              {wrappedRepoTools.length > 0 ? (
                wrappedRepoTools.map((tool) => (
                  <div key={`${tool.name}-${tool.source_path}-${tool.wrapper_kind}`} className="rounded-2xl border border-rock-blue/14 bg-kilamanjaro/35 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-pampas">{tool.name}</p>
                        <p className="mt-1 text-sm text-pampas/58">{tool.description || tool.command || "Wrapped repo tool"}</p>
                        <p className="mt-2 text-xs text-pampas/42">{tool.wrapper_kind || "wrapper"} • {tool.risk_level || "risk unknown"}</p>
                      </div>
                      <span className="rounded-full border border-rock-blue/15 bg-pampas/[0.05] px-2 py-0.5 text-[11px] uppercase tracking-[0.18em] text-pampas/52">
                        {tool.safe_to_auto_expose ? "Auto-safe" : "Review"}
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed border-rock-blue/14 bg-pampas/[0.03] px-4 py-10 text-center text-sm text-pampas/48">
                  No promoted repo tool metadata is available yet. Future import support can extend this panel cleanly.
                </div>
              )}
            </div>
          </Panel>
        </div>
      )}
    </div>
  )
}
