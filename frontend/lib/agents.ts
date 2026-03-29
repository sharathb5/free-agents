import { sanitizeImportedAgentName } from "./agent-upload"

export type Primitive = "transform" | "extract" | "classify" | "structured_agent"

/** Turn registry id like `vercel_ai` into a short display title (card fallback). */
export function humanizeAgentIdForDisplay(id: string): string {
  const s = id.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim()
  if (!s) return id
  return s.replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Home page URL with `agent` + `version` query params (opens that agent in the marketplace modal). */
export function marketplaceAgentDeepLink(agentId: string, version: string): string {
  const q = new URLSearchParams()
  const id = agentId.trim()
  const ver = version.trim()
  if (id) q.set("agent", id)
  if (ver) q.set("version", ver)
  const s = q.toString()
  return s ? `/?${s}` : "/"
}

/**
 * Marketplace card title: never show creator name as the title when it duplicates credits;
 * never show README dumps; prefer humanized agent id when name is misleading.
 */
export function marketplaceCardTitle(data: Record<string, unknown>): string {
  const raw = typeof data.name === "string" ? data.name : ""
  const id = String(data.id ?? "").trim()
  let creditsName = ""
  if (data.credits && typeof data.credits === "object" && data.credits !== null) {
    const n = (data.credits as { name?: string }).name
    if (typeof n === "string") creditsName = n.trim().toLowerCase()
  }
  const nameNorm = raw.trim().toLowerCase()
  if (id && creditsName && nameNorm === creditsName) {
    return humanizeAgentIdForDisplay(id)
  }
  const cleaned = sanitizeImportedAgentName(raw)
  if (cleaned) {
    if (
      /^repository\s*:/i.test(cleaned) ||
      /^languages\s*:/i.test(cleaned) ||
      cleaned.length > 80
    ) {
      return id ? humanizeAgentIdForDisplay(id) : cleaned.slice(0, 60)
    }
    return cleaned
  }
  if (id) return humanizeAgentIdForDisplay(id)
  return "Untitled agent"
}

export interface AgentSummary {
  id: string
  version?: string
  name: string
  description: string
  primitive: Primitive
  tags?: string[] | null
  supports_memory?: boolean
  created_at?: number
  archived?: boolean
  credits?: {
    name: string
    url?: string
  }
}

export interface AgentDetail extends AgentSummary {
  prompt?: string
  input_schema?: Record<string, any>
  output_schema?: Record<string, any>
  memory_policy?: Record<string, any> | null
}
