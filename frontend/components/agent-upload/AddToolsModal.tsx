"use client"

import * as React from "react"
import { Search, Plus } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { CatalogToolCategory, fetchCatalogToolsFlat, FlatCatalogTool } from "@/lib/agent-upload"

interface AddToolsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  categories: CatalogToolCategory[]
  selectedTools: string[]
  onAttach: (toolIds: string[]) => void
}

export function AddToolsModal({
  open,
  onOpenChange,
  categories,
  selectedTools,
  onAttach,
}: AddToolsModalProps) {
  const [query, setQuery] = React.useState("")
  const [categoryFilter, setCategoryFilter] = React.useState("all")
  const [executionKindFilter, setExecutionKindFilter] = React.useState("all")
  const [pendingSelection, setPendingSelection] = React.useState<string[]>([])
  const [remoteTools, setRemoteTools] = React.useState<FlatCatalogTool[]>([])
  const [remoteLoading, setRemoteLoading] = React.useState(false)
  const [remoteError, setRemoteError] = React.useState<string>("")

  React.useEffect(() => {
    if (!open) {
      setPendingSelection([])
      setQuery("")
      setCategoryFilter("all")
      setExecutionKindFilter("all")
      setRemoteTools([])
      setRemoteError("")
      setRemoteLoading(false)
    }
  }, [open])

  React.useEffect(() => {
    if (!open) return
    let cancelled = false
    const handle = window.setTimeout(async () => {
      try {
        setRemoteLoading(true)
        setRemoteError("")

        const response = await fetchCatalogToolsFlat({
          q: query.trim() || undefined,
          category: categoryFilter === "all" ? undefined : categoryFilter,
          execution_kind: executionKindFilter === "all" ? undefined : executionKindFilter,
          limit: 200,
        })
        if (cancelled) return
        setRemoteTools(Array.isArray(response.tools) ? response.tools : [])
      } catch (error) {
        if (cancelled) return
        setRemoteError(error instanceof Error ? error.message : "Failed to load tools")
        setRemoteTools([])
      } finally {
        if (cancelled) return
        setRemoteLoading(false)
      }
    }, 220)

    return () => {
      cancelled = true
      window.clearTimeout(handle)
    }
  }, [open, query, categoryFilter, executionKindFilter])

  const tools = remoteTools.map((tool) => ({
    id: tool.id,
    name: tool.name,
    description: tool.description || undefined,
    category: tool.category || "Other",
    execution_kind: tool.execution_kind || "general",
  }))

  const attach = () => {
    onAttach(pendingSelection)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl rounded-[28px] border-rock-blue/18 bg-kilamanjaro/96 p-0">
        <DialogHeader className="border-b border-rock-blue/12 px-6 py-5">
          <DialogTitle className="font-headline text-3xl">Add Tools</DialogTitle>
          <DialogDescription>
            Attach promoted catalog tools now. Importing a new tool or syncing a source can plug into this modal later at the same interface boundary.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-5 px-6 py-5">
          <div className="grid gap-3 md:grid-cols-[1fr_180px_180px]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-pampas/38" />
              <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search promoted tools" className="pl-10" />
            </div>
            <select
              value={categoryFilter}
              onChange={(event) => setCategoryFilter(event.target.value)}
              className="flex h-11 w-full rounded-xl border border-rock-blue/15 bg-kilamanjaro/55 px-4 py-2 text-sm text-pampas"
            >
              <option value="all">All categories</option>
              {categories.map((category) => (
                <option key={category.name} value={category.name}>
                  {category.name}
                </option>
              ))}
            </select>
            <select
              value={executionKindFilter}
              onChange={(event) => setExecutionKindFilter(event.target.value)}
              className="flex h-11 w-full rounded-xl border border-rock-blue/15 bg-kilamanjaro/55 px-4 py-2 text-sm text-pampas"
            >
              <option value="all">All execution</option>
              {[...new Set(tools.map((tool) => tool.execution_kind))].map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
          </div>

          <div className="grid max-h-[420px] gap-3 overflow-y-auto pr-1">
            {tools.map((tool) => {
              const attachedAlready = selectedTools.includes(tool.id)
              const selected = pendingSelection.includes(tool.id)
              return (
                <button
                  key={tool.id}
                  type="button"
                  disabled={attachedAlready}
                  onClick={() =>
                    setPendingSelection((current) =>
                      selected ? current.filter((toolId) => toolId !== tool.id) : [...current, tool.id]
                    )
                  }
                  className="rounded-2xl border border-rock-blue/14 bg-pampas/[0.04] p-4 text-left transition hover:border-rock-blue/24 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold text-pampas">{tool.id}</p>
                        <span className="rounded-full border border-rock-blue/14 bg-kilamanjaro/35 px-2 py-0.5 text-[11px] uppercase tracking-[0.18em] text-pampas/58">
                          {tool.category}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-pampas/62">{tool.description || "No description yet."}</p>
                    </div>
                    <div className="rounded-full border border-rock-blue/14 bg-kilamanjaro/35 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-pampas/54">
                      {attachedAlready ? "Attached" : selected ? "Selected" : tool.execution_kind}
                    </div>
                  </div>
                </button>
              )
            })}

            {remoteLoading && (
              <div className="rounded-2xl border border-dashed border-rock-blue/14 bg-pampas/[0.03] px-4 py-10 text-center text-sm text-pampas/48">
                Loading promoted tools…
              </div>
            )}

            {!remoteLoading && remoteError && (
              <div className="rounded-2xl border border-red-400/25 bg-red-500/10 px-4 py-10 text-center text-sm text-red-200">
                {remoteError}
              </div>
            )}

            {!remoteLoading && !remoteError && tools.length === 0 && (
              <div className="rounded-2xl border border-dashed border-rock-blue/14 bg-pampas/[0.03] px-4 py-10 text-center text-sm text-pampas/48">
                No promoted tools match those filters.
              </div>
            )}
          </div>

          <div className="flex items-center justify-between gap-4 border-t border-rock-blue/12 pt-4">
            <p className="text-sm text-pampas/52">TODO boundary: new tool import/upload/sync actions can slot into this modal footer later.</p>
            <Button onClick={attach} disabled={pendingSelection.length === 0}>
              <Plus className="mr-2 h-4 w-4" />
              Attach Selected
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
