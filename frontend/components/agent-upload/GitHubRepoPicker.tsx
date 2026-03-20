"use client"

import * as React from "react"
import { RefreshCw, Search, Lock, Github } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { GitHubRepoSummary } from "@/lib/agent-upload"

interface GitHubRepoPickerProps {
  repos: GitHubRepoSummary[]
  isLoading: boolean
  error?: string
  selectedRepo?: GitHubRepoSummary | null
  onSelectRepo: (repo: GitHubRepoSummary) => void
  onRefresh?: () => void
}

export function GitHubRepoPicker({
  repos,
  isLoading,
  error,
  selectedRepo,
  onSelectRepo,
  onRefresh,
}: GitHubRepoPickerProps) {
  const [query, setQuery] = React.useState("")

  const filteredRepos = repos.filter((repo) => {
    const needle = query.trim().toLowerCase()
    if (!needle) return true
    return (
      repo.full_name.toLowerCase().includes(needle) ||
      repo.name.toLowerCase().includes(needle) ||
      repo.owner_login.toLowerCase().includes(needle)
    )
  })

  return (
    <div className="rounded-[24px] border border-rock-blue/14 bg-kilamanjaro/38 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm font-semibold text-pampas">Repository picker</p>
          <p className="mt-1 text-sm text-pampas/54">
            Future OAuth wiring will populate this list from the signed-in GitHub account.
          </p>
        </div>
        {onRefresh && (
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={isLoading}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
        )}
      </div>

      <div className="relative mt-4">
        <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-pampas/38" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search repositories"
          className="pl-10"
          disabled={isLoading || repos.length === 0}
        />
      </div>

      {error && <p className="mt-3 text-sm text-red-300">{error}</p>}

      <div className="mt-4 grid max-h-[280px] gap-3 overflow-y-auto pr-1">
        {isLoading && (
          <div className="rounded-2xl border border-rock-blue/14 bg-pampas/[0.03] px-4 py-10 text-center text-sm text-pampas/52">
            Loading repositories...
          </div>
        )}

        {!isLoading && filteredRepos.map((repo) => {
          const isSelected = selectedRepo?.full_name === repo.full_name
          return (
            <button
              key={String(repo.id)}
              type="button"
              onClick={() => onSelectRepo(repo)}
              className={[
                "rounded-2xl border p-4 text-left transition",
                isSelected
                  ? "border-blue-bayoux bg-blue-bayoux/10"
                  : "border-rock-blue/14 bg-pampas/[0.04] hover:border-rock-blue/24",
              ].join(" ")}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <Github className="h-4 w-4 text-pampas/68" />
                    <p className="text-sm font-semibold text-pampas">{repo.full_name}</p>
                  </div>
                  <p className="mt-1 text-xs text-pampas/48">{repo.html_url}</p>
                </div>
                {repo.private && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-rock-blue/14 bg-kilamanjaro/35 px-2 py-0.5 text-[11px] uppercase tracking-[0.18em] text-pampas/54">
                    <Lock className="h-3 w-3" />
                    Private
                  </span>
                )}
              </div>
            </button>
          )
        })}

        {!isLoading && filteredRepos.length === 0 && (
          <div className="rounded-2xl border border-dashed border-rock-blue/14 bg-pampas/[0.03] px-4 py-10 text-center text-sm text-pampas/48">
            {repos.length === 0
              ? "No repositories loaded yet. OAuth wiring will populate this picker later."
              : "No repositories match that search."}
          </div>
        )}
      </div>
    </div>
  )
}
