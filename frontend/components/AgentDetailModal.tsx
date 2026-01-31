"use client"

import * as React from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { CodeBlock } from "@/components/CodeBlock"
import { Agent } from "@/lib/agents"
import { cn } from "@/lib/utils"
import { Copy } from "lucide-react"

interface AgentDetailModalProps {
  agent: Agent | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onCopy?: () => void
}

const primitiveColors: Record<string, string> = {
  transform: "bg-blue-bayoux/18 text-pampas border-rock-blue/20",
  extract: "bg-rock-blue/16 text-pampas border-rock-blue/20",
  classify: "bg-pampas/8 text-pampas border-rock-blue/20",
}

export function AgentDetailModal({
  agent,
  open,
  onOpenChange,
  onCopy,
}: AgentDetailModalProps) {
  if (!agent) return null

  const localRunCommand = agent.installCommand
  const dockerRunCommand = agent.dockerCommand

  const handleCopyCommand = async () => {
    await navigator.clipboard.writeText(localRunCommand)
    onCopy?.()
  }

  const handleCopyCurl = async () => {
    await navigator.clipboard.writeText(agent.exampleInvoke.curl)
    onCopy?.()
  }

  const handleCopyInputSchema = async () => {
    await navigator.clipboard.writeText(JSON.stringify(agent.inputSchema, null, 2))
    onCopy?.()
  }

  const handleCopyOutputSchema = async () => {
    await navigator.clipboard.writeText(JSON.stringify(agent.outputSchema, null, 2))
    onCopy?.()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2 mb-2 pr-10">
                <DialogTitle className="font-headline text-2xl md:text-3xl tracking-tight">
                  {agent.name}
                </DialogTitle>
                <Badge
                  variant="secondary"
                  className={cn(
                    "text-xs font-medium border",
                    primitiveColors[agent.primitive] || primitiveColors.transform
                  )}
                >
                  {agent.primitive}
                </Badge>
              </div>
              <DialogDescription className="text-base text-pampas/70">
                {agent.description}
              </DialogDescription>
            </div>
          </div>
          <div className="flex items-center gap-2 mt-4 flex-wrap">
            {agent.tags.map((tag) => (
              <Badge
                key={tag}
                variant="outline"
                className="text-xs border-rock-blue/20 bg-pampas/6 text-pampas/75"
              >
                {tag}
              </Badge>
            ))}
          </div>
        </DialogHeader>

        <Separator className="my-4" />

        <div className="flex-1 overflow-hidden">
          <Tabs defaultValue="overview" className="w-full">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="install">Get set up</TabsTrigger>
              <TabsTrigger value="api">API</TabsTrigger>
              <TabsTrigger value="schema">Schema</TabsTrigger>
            </TabsList>

            <ScrollArea className="h-[calc(90vh-350px)] max-h-[600px] mt-4">
              <TabsContent value="overview" className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold text-pampas mb-2">
                    Description
                  </h3>
                  <p className="text-pampas/75">{agent.description}</p>
                </div>
                {agent.useCases && agent.useCases.length > 0 && (
                  <div>
                    <h3 className="text-lg font-semibold text-pampas mb-2">
                      Use Cases
                    </h3>
                    <ul className="list-disc list-inside space-y-1 text-pampas/75">
                      {agent.useCases.map((useCase, idx) => (
                        <li key={idx}>{useCase}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </TabsContent>

              <TabsContent value="install" className="space-y-6">
                <p className="text-sm text-pampas/75">
                  If you haven&apos;t already, clone the repo and run <code className="font-mono text-pampas/85">make install</code> once. For real LLM output, set up OpenRouter (API key in <code className="font-mono text-pampas/85">.env</code>) — see Get set up on the home page.
                </p>

                <div className="space-y-4">
                  <div className="space-y-2">
                    <h3 className="text-lg font-semibold text-pampas mb-1">
                      Run this agent locally
                    </h3>
                    <CodeBlock code={localRunCommand} onCopy={handleCopyCommand} />
                    <p className="text-sm text-pampas/60">
                      Starts the gateway for this preset on{" "}
                      <code className="font-mono text-pampas/85">http://localhost:4280</code>.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold text-pampas/90">
                      Run with Docker (alternative)
                    </h4>
                    <CodeBlock
                      code={dockerRunCommand}
                      onCopy={async () => {
                        await navigator.clipboard.writeText(dockerRunCommand)
                        onCopy?.()
                      }}
                    />
                    <p className="text-sm text-pampas/60">
                      Runs the gateway for this preset via Docker on{" "}
                      <code className="font-mono text-pampas/85">http://localhost:4280</code>.
                    </p>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="api" className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold text-pampas mb-2">
                    Invoke Endpoint
                  </h3>
                  <CodeBlock code={agent.exampleInvoke.curl} onCopy={handleCopyCurl} />
                </div>
                <Separator />
                <div>
                  <h3 className="text-lg font-semibold text-pampas mb-2">
                    Example Input
                  </h3>
                  <CodeBlock
                    code={JSON.stringify(agent.exampleInvoke.input, null, 2)}
                  />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-pampas mb-2">
                    Example Output
                  </h3>
                  <CodeBlock
                    code={JSON.stringify(agent.exampleInvoke.output, null, 2)}
                  />
                </div>
              </TabsContent>

              <TabsContent value="schema" className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold text-pampas mb-2">
                    Input Schema
                  </h3>
                  <div className="relative">
                    <CodeBlock
                      code={JSON.stringify(agent.inputSchema, null, 2)}
                      onCopy={handleCopyInputSchema}
                    />
                  </div>
                </div>
                <Separator />
                <div>
                  <h3 className="text-lg font-semibold text-pampas mb-2">
                    Output Schema
                  </h3>
                  <div className="relative">
                    <CodeBlock
                      code={JSON.stringify(agent.outputSchema, null, 2)}
                      onCopy={handleCopyOutputSchema}
                    />
                  </div>
                </div>
              </TabsContent>
            </ScrollArea>
          </Tabs>
        </div>

        <Separator className="my-4" />

        <div className="flex items-center justify-end gap-2">
          <Button
            variant="outline"
            onClick={() => {
              navigator.clipboard.writeText(agent.exampleInvoke.curl)
              onCopy?.()
            }}
            aria-label="Copy example curl for this agent"
          >
            <Copy className="h-4 w-4 mr-2" />
            Copy API Snippet
          </Button>
          <Button
            onClick={handleCopyCommand}
            aria-label="Copy the local run command for this agent"
          >
            <Copy className="h-4 w-4 mr-2" />
            Copy run command
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
