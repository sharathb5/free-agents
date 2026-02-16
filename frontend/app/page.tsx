"use client"

import * as React from "react"
import { Plus, Search } from "lucide-react"
import Link from "next/link"
import { Input } from "@/components/ui/input"
import { AgentCard } from "@/components/AgentCard"
import { AgentDetailModal } from "@/components/AgentDetailModal"
import { Toast } from "@/components/ui/toast"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { CodeBlock } from "@/components/CodeBlock"
import { Card } from "@/components/ui/card"
import { SignInButton, SignedIn, SignedOut, UserButton, useAuth } from "@clerk/nextjs"
import { AgentSummary, Primitive } from "@/lib/agents"

export default function MarketplacePage() {
  const { isSignedIn, getToken } = useAuth()
  const [searchQuery, setSearchQuery] = React.useState("")
  const [selectedPrimitive, setSelectedPrimitive] = React.useState<Primitive | "all">("all")
  const [selectedAgent, setSelectedAgent] = React.useState<AgentSummary | null>(null)
  const [isModalOpen, setIsModalOpen] = React.useState(false)
  const [isSetupOpen, setIsSetupOpen] = React.useState(false)
  const [setupOs, setSetupOs] = React.useState<"mac_linux" | "windows">("mac_linux")
  const [toastMessage, setToastMessage] = React.useState("")
  const [showToast, setShowToast] = React.useState(false)
  const [agents, setAgents] = React.useState<AgentSummary[]>([])
  const [agentsLoading, setAgentsLoading] = React.useState(false)
  const [agentsError, setAgentsError] = React.useState<string | null>(null)
  const [showMine, setShowMine] = React.useState(false)
  const [showArchived, setShowArchived] = React.useState(false)
  const [ownedIds, setOwnedIds] = React.useState<Set<string>>(new Set())
  const searchRef = React.useRef<HTMLInputElement | null>(null)
  const initialCacheLoaded = React.useRef(false)
  const requestIdRef = React.useRef(0)

  const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:4280"
  const AGENTS_CACHE_KEY = "agent-catalog:agents:latest"

  const REPO_CLONE_COMMAND = "pipx install agent-toolbox"
  const PIPX_SETUP_COMMAND =
    setupOs === "windows"
      ? "py -m pip install --user pipx\npy -m pipx ensurepath"
      : "python3 -m pip install --user pipx\npython3 -m pipx ensurepath"
  const PROJECT_SETUP_COMMAND = "agent-toolbox setup"
  const LOCAL_RUN_EXAMPLE =
    setupOs === "windows"
      ? "$env:AGENT_PRESET=\"summarizer\"\nagent-toolbox"
      : "AGENT_PRESET=summarizer agent-toolbox"

  React.useEffect(() => {
    if (showMine) return
    if (initialCacheLoaded.current) return
    initialCacheLoaded.current = true
    try {
      const cached = localStorage.getItem(AGENTS_CACHE_KEY)
      if (!cached) return
      const payload = JSON.parse(cached)
      if (Array.isArray(payload?.agents)) {
        setAgents(payload.agents)
      }
    } catch {
      // Ignore cache parse errors
    }
  }, [showMine])

  const loadAgents = React.useCallback(
    async (opts?: { silent?: boolean }) => {
      const requestId = ++requestIdRef.current
      if (!opts?.silent) {
        setAgentsLoading(true)
      }
      setAgentsError(null)
      try {
        if (showMine) {
          if (!isSignedIn) {
            setAgents([])
            setAgentsError("Sign in to see agents you own.")
            setOwnedIds(new Set())
            return
          }
          const token = await getToken({
            template: process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE || undefined,
          })
          if (!token) {
            setAgents([])
            setAgentsError("Missing session token. Please sign in again.")
            return
          }
          const includeArchivedParam = showArchived ? "?include_archived=true" : ""
          const res = await fetch(`${GATEWAY_URL}/agents/mine${includeArchivedParam}`, {
            headers: { Authorization: `Bearer ${token}` },
          })
          const data = await res.json()
          const nextAgents = Array.isArray(data?.agents)
            ? data.agents
            : Array.isArray(data)
              ? data
              : []
          if (requestIdRef.current !== requestId) return
          if (res.ok) {
            setAgents(nextAgents)
            if (!Array.isArray(data?.agents) && !Array.isArray(data)) {
              setAgentsError("Unexpected response shape from /agents/mine")
            }
            setOwnedIds(new Set(nextAgents.map((agent: AgentSummary) => agent.id)))
          } else {
            setAgentsError(data?.error?.message || `Failed (${res.status})`)
            setOwnedIds(new Set())
          }
        } else {
          const res = await fetch(`${GATEWAY_URL}/agents?latest_only=true`)
          const data = await res.json()
          const nextAgents = Array.isArray(data?.agents)
            ? data.agents
            : Array.isArray(data)
              ? data
              : []
          if (requestIdRef.current !== requestId) return
          if (res.ok) {
            setAgents(nextAgents)
            if (!Array.isArray(data?.agents) && !Array.isArray(data)) {
              setAgentsError("Unexpected response shape from /agents")
            }
            try {
              localStorage.setItem(
                AGENTS_CACHE_KEY,
                JSON.stringify({ agents: nextAgents, cached_at: Date.now() })
              )
            } catch {
              // Ignore storage errors
            }
            if (isSignedIn) {
              try {
                const token = await getToken({
                  template: process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE || undefined,
                })
                if (token) {
                  const mineRes = await fetch(`${GATEWAY_URL}/agents/mine?include_archived=true`, {
                    headers: { Authorization: `Bearer ${token}` },
                  })
                  const mineData = await mineRes.json()
                  if (mineRes.ok && Array.isArray(mineData?.agents)) {
                    setOwnedIds(new Set(mineData.agents.map((agent: AgentSummary) => agent.id)))
                  } else if (!mineRes.ok) {
                    setOwnedIds(new Set())
                  }
                } else {
                  setOwnedIds(new Set())
                }
              } catch {
                setOwnedIds(new Set())
              }
            } else {
              setOwnedIds(new Set())
            }
          } else {
            setAgentsError(data?.error?.message || `Failed (${res.status})`)
            setOwnedIds(new Set())
          }
        }
      } catch (e) {
        if (requestIdRef.current !== requestId) return
        setAgentsError(e instanceof Error ? e.message : "Request failed")
        setOwnedIds(new Set())
      } finally {
        if (requestIdRef.current !== requestId) return
        if (!opts?.silent) {
          setAgentsLoading(false)
        }
      }
    },
    [getToken, isSignedIn, showMine, showArchived, GATEWAY_URL]
  )

  React.useEffect(() => {
    loadAgents()
  }, [loadAgents])

  React.useEffect(() => {
    if (showMine) return
    const streamUrl = `${GATEWAY_URL}/agents/updates/stream`
    const eventSource = new EventSource(streamUrl)
    const handleAgentCreated = () => {
      loadAgents({ silent: true })
    }
    eventSource.addEventListener("agent_created", handleAgentCreated)
    return () => {
      eventSource.removeEventListener("agent_created", handleAgentCreated)
      eventSource.close()
    }
  }, [GATEWAY_URL, loadAgents, showMine])

  const filteredAgents = agents.filter((agent) => {
    const matchesSearch =
      (agent.name || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (agent.description || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (agent.tags || []).some((tag) => tag.toLowerCase().includes(searchQuery.toLowerCase()))
    const matchesPrimitive =
      selectedPrimitive === "all" || agent.primitive === selectedPrimitive
    return matchesSearch && matchesPrimitive
  })

  const handleAgentClick = (agent: AgentSummary) => {
    setSelectedAgent(agent)
    setIsModalOpen(true)
  }

  const handleCopy = (msg: string = "Copied to clipboard!") => {
    setToastMessage(msg)
    setShowToast(true)
  }

  const primitives: Array<{ value: Primitive | "all"; label: string }> = [
    { value: "all", label: "All" },
    { value: "transform", label: "Transform" },
    { value: "extract", label: "Extract" },
    { value: "classify", label: "Classify" },
  ]

  return (
    <div className="min-h-screen selection-palette">
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -top-40 left-1/2 h-[520px] w-[900px] -translate-x-1/2 rounded-full bg-blue-bayoux/25 blur-[120px]" />
          <div className="absolute top-24 right-[-120px] h-[320px] w-[320px] rounded-full bg-rock-blue/14 blur-[90px]" />
        </div>

        <div className="mx-auto max-w-7xl px-4 md:px-8 pt-10 pb-10">
          <div className="flex flex-col gap-7">
            <div className="flex items-center justify-between gap-4">
              <div className="inline-flex w-fit items-center gap-2 rounded-full border border-rock-blue/18 bg-pampas/6 px-3 py-1 text-xs font-semibold tracking-[0.18em] text-pampas/75">
                LOCAL AGENT MARKETPLACE
              </div>
              <div className="flex items-center gap-3">
                <SignedOut>
                  <SignInButton>
                    <button className="rounded-full border border-rock-blue/20 bg-pampas/8 px-4 py-2 text-xs font-semibold tracking-[0.18em] text-pampas/75 uppercase">
                      Sign in
                    </button>
                  </SignInButton>
                </SignedOut>
                <SignedIn>
                  <UserButton afterSignOutUrl="/" />
                </SignedIn>
              </div>
            </div>

            <div className="max-w-3xl">
              <h1 className="font-headline text-4xl md:text-6xl leading-[1.05] tracking-tight text-pampas">
                Run AI agents locally in one command.
              </h1>
              <p className="mt-4 text-base md:text-lg text-pampas/70">
                Install via pipx (or venv) → set up once → pick a preset → call{" "}
                <span className="font-mono text-pampas/85">/invoke</span>.
              </p>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <Button
                onClick={() => setIsSetupOpen(true)}
                className="h-11 rounded-xl"
              >
                Get set up
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* Marketplace */}
      <main id="marketplace" className="mx-auto max-w-7xl px-4 md:px-8 pb-14">
        {/* Search + filters panel */}
        <div className="rounded-2xl border border-rock-blue/15 bg-pampas/6 p-4 md:p-5 shadow-[0_34px_90px_-70px_rgba(159,178,205,0.55)] backdrop-blur">
          <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-center">
            <div className="relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-pampas/45" />
              <Input
                ref={searchRef}
                type="text"
                placeholder="Search agents by name, description, or tags..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-11"
              />
            </div>
            <div className="flex flex-wrap gap-2 md:justify-end">
              <SignedOut>
                <SignInButton>
                  <button
                    className={[
                      "h-10 rounded-full px-4 text-sm font-medium transition-all border",
                      "bg-pampas/5 text-pampas/75 border-rock-blue/15 hover:bg-pampas/8 hover:text-pampas",
                    ].join(" ")}
                  >
                    Sign in
                  </button>
                </SignInButton>
              </SignedOut>
              <SignedIn>
                <button
                  onClick={() => setShowMine((prev) => !prev)}
                  className={[
                    "h-10 rounded-full px-4 text-sm font-medium transition-all border",
                    showMine
                      ? "bg-blue-bayoux/90 text-pampas border-rock-blue/18 shadow-[0_20px_50px_-40px_rgba(159,178,205,0.55)]"
                      : "bg-pampas/5 text-pampas/75 border-rock-blue/15 hover:bg-pampas/8 hover:text-pampas",
                  ].join(" ")}
                >
                  By you
                </button>
              </SignedIn>
              {showMine && (
                <button
                  onClick={() => setShowArchived((prev) => !prev)}
                  className={[
                    "h-10 rounded-full px-4 text-sm font-medium transition-all border",
                    showArchived
                      ? "bg-amber-900/70 text-pampas border-amber-500/40 shadow-[0_20px_50px_-40px_rgba(255,200,120,0.35)]"
                      : "bg-pampas/5 text-pampas/75 border-rock-blue/15 hover:bg-pampas/8 hover:text-pampas",
                  ].join(" ")}
                >
                  Archived
                </button>
              )}
              {primitives.map((primitive) => {
                const active = selectedPrimitive === primitive.value
                return (
                  <button
                    key={primitive.value}
                    onClick={() => setSelectedPrimitive(primitive.value)}
                    className={[
                      "h-10 rounded-full px-4 text-sm font-medium transition-all border",
                      active
                        ? "bg-blue-bayoux/90 text-pampas border-rock-blue/18 shadow-[0_20px_50px_-40px_rgba(159,178,205,0.55)]"
                        : "bg-pampas/5 text-pampas/75 border-rock-blue/15 hover:bg-pampas/8 hover:text-pampas",
                    ].join(" ")}
                  >
                    {primitive.label}
                  </button>
                )
              })}
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-pampas/55">
            <div>
              Showing <span className="text-pampas/75">{filteredAgents.length}</span> of{" "}
              <span className="text-pampas/75">{agents.length}</span> agents
            </div>
            {agentsLoading && <span className="text-pampas/55">Loading…</span>}
            {agentsError && <span className="text-red-400">{agentsError}</span>}
          </div>
        </div>

        {/* Grid */}
        <div className="mt-8">
          {filteredAgents.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 items-stretch">
              <Link
                href="/upload"
                className="group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rock-blue/60 focus-visible:ring-offset-2 focus-visible:ring-offset-kilamanjaro rounded-2xl"
              >
                <div className="relative h-full min-h-[260px] rounded-2xl border border-rock-blue/15 bg-white/5 backdrop-blur-sm transition-all hover:-translate-y-1 hover:border-rock-blue/30">
                  <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-white/5 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
                  <div className="relative flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
                    <div className="flex h-14 w-14 items-center justify-center rounded-full border border-white/30 bg-white/10 text-white/70">
                      <Plus className="h-7 w-7" />
                    </div>
                    <div className="text-lg font-semibold tracking-tight text-pampas/85">
                      Add your own agent
                    </div>
                    <div className="text-xs text-pampas/55">
                      Upload a custom spec
                    </div>
                  </div>
                </div>
              </Link>
              {filteredAgents.map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  onClick={() => handleAgentClick(agent)}
                  onCopy={() => handleCopy("Install command copied")}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-rock-blue/15 bg-pampas/6 p-10 text-center">
              <p className="text-pampas/75 text-lg">No agents found.</p>
              <p className="text-pampas/55 text-sm mt-2">Try adjusting your search or filters.</p>
            </div>
          )}
        </div>
      </main>

      {/* Global "Get set up" dialog */}
      <Dialog open={isSetupOpen} onOpenChange={setIsSetupOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="font-headline text-2xl tracking-tight">
              Get set up locally
            </DialogTitle>
            <DialogDescription className="text-sm text-pampas/75">
              Follow these steps once per machine, then use any agent from the catalog.
            </DialogDescription>
          </DialogHeader>

          <div className="mt-4 space-y-4 text-sm text-pampas/85">
            <div>
              <p className="font-semibold">Choose your OS</p>
              <div className="mt-2 inline-flex rounded-lg border border-rock-blue/30 bg-pampas/5 p-1">
                <button
                  type="button"
                  onClick={() => setSetupOs("mac_linux")}
                  className={`rounded-md px-3 py-1.5 text-xs ${
                    setupOs === "mac_linux"
                      ? "bg-rock-blue/25 text-pampas"
                      : "text-pampas/70 hover:text-pampas"
                  }`}
                >
                  macOS/Linux
                </button>
                <button
                  type="button"
                  onClick={() => setSetupOs("windows")}
                  className={`rounded-md px-3 py-1.5 text-xs ${
                    setupOs === "windows"
                      ? "bg-rock-blue/25 text-pampas"
                      : "text-pampas/70 hover:text-pampas"
                  }`}
                >
                  Windows
                </button>
              </div>
            </div>

            <div>
              <p className="font-semibold">Step 1 – Install CLI (pipx recommended)</p>
              <div className="mt-1">
                <CodeBlock code={REPO_CLONE_COMMAND} />
              </div>
              <p className="mt-1 text-xs text-pampas/60">
                Requires <code className="font-mono text-pampas/85">Python 3.10+</code>. If pipx is not installed yet, run:
              </p>
              <div className="mt-1">
                <CodeBlock code={PIPX_SETUP_COMMAND} />
              </div>
            </div>

            <div>
              <p className="font-semibold">Step 2 – Print setup guidance</p>
              <div className="mt-1">
                <CodeBlock code={PROJECT_SETUP_COMMAND} />
              </div>
              <p className="mt-1 text-xs text-pampas/60">
                Shows environment variable and API key instructions.
              </p>
            </div>

            <div>
              <p className="font-semibold">Step 3 – Configure LLM (OpenRouter)</p>
              <p className="mt-1 text-xs text-pampas/65">
                For real LLM output, get an API key from OpenRouter (one key for many models), then
                add to a <code className="font-mono text-pampas/85">.env</code> file in the project
                root:
              </p>
              <div className="mt-1">
                <CodeBlock
                  code={`PROVIDER=openrouter\nOPENROUTER_API_KEY=YOUR_KEY_HERE\nOPENROUTER_MODEL=openai/gpt-4o-mini`}
                />
              </div>
              <p className="mt-1 text-xs text-pampas/60">
                Get your key at{" "}
                <a
                  href="https://openrouter.ai/keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-rock-blue underline hover:text-pampas"
                >
                  openrouter.ai/keys
                </a>
                . Run <code className="font-mono text-pampas/85">agent-toolbox setup</code> in your
                project folder to see the full setup block.
              </p>
            </div>

            <div>
              <p className="font-semibold">Step 4 – Run an agent</p>
              <p className="mt-1 text-xs text-pampas/65">
                Pick an agent from the catalog and copy its run command. For example:
              </p>
              <div className="mt-1 space-y-2">
                <CodeBlock code={LOCAL_RUN_EXAMPLE} />
              </div>
              <p className="mt-1 text-xs text-pampas/60">
                This starts the gateway on{" "}
                <code className="font-mono text-pampas/85">http://localhost:4280</code>. Use{" "}
                <code className="font-mono text-pampas/85">Ctrl+C</code>{" "}
                to stop.
              </p>
              <p className="mt-2 text-xs text-pampas/60">
                Session memory is available via CLI calls (
                <code className="font-mono text-pampas/85">POST /sessions</code> and{" "}
                <code className="font-mono text-pampas/85">POST /sessions/&lt;id&gt;/events</code>)
                when you need it.
              </p>
              <p className="mt-2 text-xs text-pampas/65">
                Having issues?{" "}
                <Link
                  href="/troubleshooting"
                  className="text-rock-blue underline hover:text-pampas"
                >
                  Open troubleshooting
                </Link>
                .
              </p>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Detail Modal */}
      <AgentDetailModal
        agent={selectedAgent}
        open={isModalOpen}
        onOpenChange={setIsModalOpen}
        onCopy={() => handleCopy()}
        onArchived={() => loadAgents({ silent: true })}
        canManage={
          !!selectedAgent &&
          (showMine || ownedIds.has(selectedAgent.id))
        }
      />

      {/* Toast */}
      <Toast
        message={toastMessage}
        isVisible={showToast}
        onClose={() => setShowToast(false)}
      />
    </div>
  )
}
