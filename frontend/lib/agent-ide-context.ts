const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:4280"

/** Shown in the marketplace detail modal and as default “key use cases” for IDE context. */
export const DEFAULT_AGENT_USE_CASES = [
  "Summarize the repository architecture",
  "Explain the API surface and common usage patterns",
  "Identify important scripts, commands, and development workflows",
] as const

const CURSOR_DEEPLINK_MAX_TOTAL_LENGTH = 8000
const CLAUDE_WEB_URL_MAX_TOTAL_LENGTH = 8000

const CURSOR_PROMPT_PREFIX = "cursor://anysphere.cursor-deeplink/prompt?text="

export interface AgentIdeContextInput {
  prompt: string
  agentId: string
  version?: string
  description: string
  useCases: readonly string[]
  /** GitHub URL, `owner/repo`, or `git@github.com:owner/repo.git` — used for the Claude “codebase” prompt. */
  sourceRepo?: string
}

/**
 * Resolves a display slug `owner/repo` for Claude context. Falls back when missing or unparseable.
 */
export function normalizeGithubOwnerRepo(input?: string | null): string {
  if (!input?.trim()) return "unknown/unknown"
  const s = input.trim()
  const gitSsh = /^git@github\.com:([^/]+)\/(.+?)(\.git)?$/i.exec(s)
  if (gitSsh) {
    return `${gitSsh[1]}/${gitSsh[2].replace(/\.git$/i, "")}`
  }
  try {
    const u = new URL(s.includes("://") ? s : `https://${s}`)
    const host = u.hostname.replace(/^www\./, "")
    if (host === "github.com") {
      const parts = u.pathname
        .replace(/^\//, "")
        .replace(/\.git$/i, "")
        .split("/")
        .filter(Boolean)
      if (parts.length >= 2) return `${parts[0]}/${parts[1]}`
    }
  } catch {
    /* fall through */
  }
  if (/^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/.test(s)) return s
  return "unknown/unknown"
}

/**
 * Cursor: help the developer call the Free Agents API from their project.
 */
export function buildCursorPromptText(input: AgentIdeContextInput): string {
  const id = input.agentId.trim()
  const ver = input.version?.trim() || "(not specified)"
  const desc = input.description.trim() || "(none)"
  const prompt = input.prompt.trim() || "(empty)"
  const base = GATEWAY_URL.replace(/\/$/, "")
  return [
    "I want to integrate this Free Agents API into my code.",
    "",
    `Agent ID: ${id}`,
    `Version: ${ver}`,
    `Description: ${desc}`,
    "",
    "Run it locally:",
    `AGENT_PRESET=${id} agent-toolbox`,
    "",
    "Invoke endpoint:",
    `POST ${base}/agents/${id}/invoke`,
    "",
    "Example curl:",
    `curl -X POST ${base}/agents/${id}/invoke \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"input": {"question": "your question here"}}'`,
    "",
    "System prompt context:",
    prompt,
    "",
    "Help me write code to call this agent, handle the response, and integrate it into my project.",
  ].join("\n")
}

function buildClaudeIdePromptText(input: AgentIdeContextInput): string {
  const slug = normalizeGithubOwnerRepo(input.sourceRepo)
  const prompt = input.prompt.trim() || "(empty)"
  const useCasesBlock = input.useCases.map((u) => `- ${u}`).join("\n")
  return [
    `I'm working with an AI agent built from the ${slug} codebase.`,
    "",
    "Here's what it knows about:",
    prompt,
    "",
    "Key use cases:",
    useCasesBlock,
    "",
    "Help me understand how this codebase works, what the main components are, and how I can use or extend this agent.",
  ].join("\n")
}

/**
 * Claude web new-chat URL with prefilled query (max length enforced on the full URL).
 */
export function buildClaudeNewChatUrl(input: AgentIdeContextInput): string {
  const body = buildClaudeIdePromptText(input)
  return encodeClaudeWebChatUrl(body)
}

function encodeClaudeWebChatUrl(promptText: string): string {
  const prefix = "https://claude.ai/new?q="
  const body = binarySearchMaxSlice(promptText, prefix, CLAUDE_WEB_URL_MAX_TOTAL_LENGTH)
  return prefix + encodeURIComponent(body)
}

function binarySearchMaxSlice(
  fullText: string,
  prefixBeforeEncodedPayload: string,
  maxTotalLength: number
): string {
  let lo = 0
  let hi = fullText.length
  let best = ""
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2)
    const slice = fullText.slice(0, mid)
    const candidate = prefixBeforeEncodedPayload + encodeURIComponent(slice)
    if (candidate.length <= maxTotalLength) {
      best = slice
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  if (best.length >= fullText.length) return best
  const suffix = "\n\n[... truncated for link length limit]"
  let withNote = best + suffix
  while (withNote.length > 0) {
    const candidate = prefixBeforeEncodedPayload + encodeURIComponent(withNote)
    if (candidate.length <= maxTotalLength) return withNote
    withNote = withNote.slice(0, Math.floor(withNote.length * 0.9))
  }
  return best
}

/**
 * Official Cursor prompt deeplink (see https://cursor.com/docs/integrations/deeplinks).
 * Max URL length 8000 characters total.
 */
export function buildCursorPromptDeeplink(promptText: string): string {
  const body = binarySearchMaxSlice(promptText, CURSOR_PROMPT_PREFIX, CURSOR_DEEPLINK_MAX_TOTAL_LENGTH)
  return CURSOR_PROMPT_PREFIX + encodeURIComponent(body)
}

/**
 * Browsers cannot reliably report whether `cursor://` will be handled; warn in environments that often block custom schemes.
 */
export function shouldWarnAboutIdeCustomLinks(): boolean {
  if (typeof window === "undefined") return false
  const ua = window.navigator.userAgent || ""
  if (/FBAN|FBAV|Instagram|Line\/|LinkedInApp|Twitter/i.test(ua)) return true
  if (!window.isSecureContext) return true
  return false
}

export function exampleLocalRunCommand(agentId: string, os: "mac_linux" | "windows"): string {
  return os === "windows"
    ? `$env:AGENT_PRESET=\"${agentId}\"\nagent-toolbox`
    : `AGENT_PRESET=${agentId} agent-toolbox`
}

export function exampleInvokeCurl(agentId: string, exampleInput: Record<string, unknown>): string {
  return `curl -X POST ${GATEWAY_URL}/agents/${agentId}/invoke \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify({ input: exampleInput }, null, 2)}'`
}
