"use client"

import * as React from "react"
import { Search } from "lucide-react"
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
import { agents, Agent, Primitive } from "@/lib/agents"

export default function MarketplacePage() {
  const [searchQuery, setSearchQuery] = React.useState("")
  const [selectedPrimitive, setSelectedPrimitive] = React.useState<Primitive | "all">("all")
  const [selectedAgent, setSelectedAgent] = React.useState<Agent | null>(null)
  const [isModalOpen, setIsModalOpen] = React.useState(false)
  const [isSetupOpen, setIsSetupOpen] = React.useState(false)
  const [toastMessage, setToastMessage] = React.useState("")
  const [showToast, setShowToast] = React.useState(false)
  const searchRef = React.useRef<HTMLInputElement | null>(null)

  const REPO_CLONE_COMMAND = "git clone <REPO_URL> && cd agent-toolbox"
  const PROJECT_SETUP_COMMAND = "make install"
  const LOCAL_RUN_EXAMPLE = "AGENT_PRESET=summarizer make run"
  const DOCKER_RUN_EXAMPLE = "make docker-up AGENT=summarizer"

  const filteredAgents = agents.filter((agent) => {
    const matchesSearch =
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.tags.some((tag) => tag.toLowerCase().includes(searchQuery.toLowerCase()))
    const matchesPrimitive =
      selectedPrimitive === "all" || agent.primitive === selectedPrimitive
    return matchesSearch && matchesPrimitive
  })

  const handleAgentClick = (agent: Agent) => {
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

        <div className="mx-auto max-w-7xl px-4 md:px-8 pt-14 pb-10">
          <div className="flex flex-col gap-7">
            <div className="inline-flex w-fit items-center gap-2 rounded-full border border-rock-blue/18 bg-pampas/6 px-3 py-1 text-xs font-semibold tracking-[0.18em] text-pampas/75">
              LOCAL AGENT MARKETPLACE
            </div>

            <div className="max-w-3xl">
              <h1 className="font-headline text-4xl md:text-6xl leading-[1.05] tracking-tight text-pampas">
                Run AI agents locally in one command.
              </h1>
              <p className="mt-4 text-base md:text-lg text-pampas/70">
                Clone the repo → set up once → pick a preset → call{" "}
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
          <div className="mt-4 text-xs text-pampas/55">
            Showing <span className="text-pampas/75">{filteredAgents.length}</span> of{" "}
            <span className="text-pampas/75">{agents.length}</span> agents
          </div>
        </div>

        {/* Grid */}
        <div className="mt-8">
          {filteredAgents.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 items-stretch">
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
              <p className="font-semibold">Step 1 – Clone the repo</p>
              <div className="mt-1">
                <CodeBlock code={REPO_CLONE_COMMAND} />
              </div>
            </div>

            <div>
              <p className="font-semibold">Step 2 – Install dependencies (once)</p>
              <div className="mt-1">
                <CodeBlock code={PROJECT_SETUP_COMMAND} />
              </div>
              <p className="mt-1 text-xs text-pampas/60">
                Creates a <code className="font-mono text-pampas/85">.venv</code> and installs Python
                requirements.
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
                . Run <code className="font-mono text-pampas/85">agent-toolbox setup</code> in the
                repo to see the full setup block.
              </p>
            </div>

            <div>
              <p className="font-semibold">Step 4 – Run an agent</p>
              <p className="mt-1 text-xs text-pampas/65">
                Pick an agent from the catalog and copy its run command. For example:
              </p>
              <div className="mt-1 space-y-2">
                <CodeBlock code={LOCAL_RUN_EXAMPLE} />
                <CodeBlock code={DOCKER_RUN_EXAMPLE} />
              </div>
              <p className="mt-1 text-xs text-pampas/60">
                Both start the gateway on{" "}
                <code className="font-mono text-pampas/85">http://localhost:4280</code>. Use{" "}
                <code className="font-mono text-pampas/85">make docker-down</code> to stop Docker.
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
