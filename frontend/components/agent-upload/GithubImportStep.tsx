"use client"

import * as React from "react"
import { Loader2, Github, Link2, PlugZap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { GitHubConnectionState, GitHubRepoSummary } from "@/lib/agent-upload"
import { GitHubRepoPicker } from "./GitHubRepoPicker"

interface GithubImportStepProps {
  repoUrl: string
  onRepoUrlChange: (value: string) => void
  onStartImport: () => void
  isLoading: boolean
  progressLabel: string
  progressValue: number
  error?: string
  githubConnectionState?: GitHubConnectionState
  githubRepos?: GitHubRepoSummary[]
  githubReposLoading?: boolean
  githubReposError?: string
  selectedGitHubRepo?: GitHubRepoSummary | null
  onConnectGitHub?: () => void
  onRefreshGitHubRepos?: () => void
  onSelectGitHubRepo?: (repo: GitHubRepoSummary) => void
}

export function GithubImportStep({
  repoUrl,
  onRepoUrlChange,
  onStartImport,
  isLoading,
  progressLabel,
  progressValue,
  error,
  githubConnectionState,
  githubRepos = [],
  githubReposLoading = false,
  githubReposError,
  selectedGitHubRepo,
  onConnectGitHub,
  onRefreshGitHubRepos,
  onSelectGitHubRepo,
}: GithubImportStepProps) {
  const [showPasteUrl, setShowPasteUrl] = React.useState(false)
  const connectionState = githubConnectionState ?? {
    provider: "github" as const,
    status: "disconnected" as const,
    message: "OAuth scaffolding only. Paste URL remains the active import path for now.",
    oauth_configured: false,
  }
  const stages = [
    "Connecting to repository",
    "Extracting tools",
    "Parsing agent details",
    "Generating recommendations",
  ]

  return (
    <div className="grid gap-6">
      <div className="rounded-[28px] border border-rock-blue/16 bg-pampas/[0.045] p-6 shadow-[0_36px_90px_-70px_rgba(159,178,205,0.5)]">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-rock-blue/15 bg-kilamanjaro/35 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-pampas/62">
              <Github className="h-3.5 w-3.5" />
              GitHub Source
            </div>
            <h2 className="font-headline text-3xl text-pampas">Import from a repository</h2>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-pampas/68">
              Connect GitHub will become the primary path here. Paste URL stays available below as the current active fallback.
            </p>
          </div>
          <div className="text-xs text-pampas/48">This step now exposes safe extension points for future OAuth and repo selection.</div>
        </div>

        <div className="mt-6 rounded-[24px] border border-rock-blue/14 bg-kilamanjaro/38 p-5 shadow-[inset_0_1px_0_rgba(240,237,232,0.04)]">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-pampas/46">
                Primary path
              </p>
              <h3 className="mt-2 text-2xl font-semibold text-pampas">Connect GitHub</h3>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-pampas/60">
                Select a repository from your GitHub account once OAuth and repo listing are wired. This pass only adds the integration boundary.
              </p>
            </div>
            <Button
              onClick={onConnectGitHub}
              disabled
              className="min-w-44"
              title="Scaffold only. OAuth is not wired yet."
            >
              <PlugZap className="mr-2 h-4 w-4" />
              Connect GitHub
            </Button>
          </div>

          <div className="mt-4 rounded-2xl border border-rock-blue/12 bg-pampas/[0.04] px-4 py-3 text-sm text-pampas/56">
            {connectionState.message || "GitHub OAuth will connect here later."}
          </div>

          <div className="mt-4">
            <GitHubRepoPicker
              repos={githubRepos}
              isLoading={githubReposLoading}
              error={githubReposError}
              selectedRepo={selectedGitHubRepo}
              onSelectRepo={onSelectGitHubRepo || (() => {})}
              onRefresh={onRefreshGitHubRepos}
            />
          </div>
        </div>

        <div className="mt-6 flex items-center justify-start">
          <button
            type="button"
            onClick={() => setShowPasteUrl((current) => !current)}
            className="rounded-full border border-rock-blue/16 bg-kilamanjaro/35 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-pampas/68 transition hover:border-rock-blue/28 hover:text-pampas"
          >
            {showPasteUrl ? "Back to GitHub" : "Paste URL"}
          </button>
        </div>

        {showPasteUrl && (
          <div className="mt-4 rounded-[24px] border border-rock-blue/14 bg-kilamanjaro/38 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-pampas/48">
              Or paste a public repo URL
            </p>
            <div className="mt-3 flex flex-col gap-3 md:flex-row">
              <div className="relative flex-1">
                <Link2 className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-pampas/38" />
                <Input
                  value={repoUrl}
                  onChange={(event) => onRepoUrlChange(event.target.value)}
                  placeholder="https://github.com/owner/repo"
                  className="pl-10"
                  disabled={isLoading}
                />
              </div>
              <Button onClick={onStartImport} disabled={isLoading || !repoUrl.trim()} className="min-w-40">
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Parsing
                  </>
                ) : (
                  "Start Import"
                )}
              </Button>
            </div>
          </div>
        )}

        {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
      </div>

      {(isLoading || progressValue > 0) && (
        <div className="rounded-[28px] border border-rock-blue/16 bg-kilamanjaro/45 p-6 shadow-[inset_0_1px_0_rgba(240,237,232,0.04)]">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-pampas">{progressLabel}</p>
              <p className="mt-1 text-sm text-pampas/58">The import will advance into Details automatically when parsing finishes.</p>
            </div>
            {isLoading && <Loader2 className="h-5 w-5 animate-spin text-rock-blue" />}
          </div>
          <div className="mt-5 h-3 overflow-hidden rounded-full bg-pampas/8">
            <div
              className="h-full rounded-full bg-gradient-to-r from-blue-bayoux via-rock-blue to-pampas/85 transition-all duration-500"
              style={{ width: `${progressValue}%` }}
            />
          </div>
          <div className="mt-5 grid gap-2 md:grid-cols-4">
            {stages.map((stage) => {
              const active = stage === progressLabel
              const complete = stages.indexOf(stage) < stages.indexOf(progressLabel)
              return (
                <div
                  key={stage}
                  className="rounded-2xl border border-rock-blue/12 bg-pampas/[0.04] px-3 py-3 text-sm"
                >
                  <p className={complete ? "text-pampas/86" : active ? "text-pampas" : "text-pampas/48"}>{stage}</p>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
