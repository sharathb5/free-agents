"use client"

export const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:4280"

export type UploadFlowPath = "build" | "github"

export interface UploadAgentDraft {
  id: string
  version: string
  name: string
  description: string
  primitive: "transform" | "extract" | "classify" | "structured_agent"
  tags: string[]
  credits: {
    name: string
    url?: string
  }
  prompt: string
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  supports_memory: boolean
  memory_policy?: {
    mode: string
    max_messages: number
    max_chars: number
  }
}

export interface FlatCatalogTool {
  id: string
  name: string
  description?: string | null
  category?: string | null
  execution_kind?: string | null
  confidence?: number | null
  source_repo?: string | null
  source_path?: string | null
  promotion_reason?: string | null
}

export interface CatalogTool {
  tool_id: string
  category: string
  description?: string
  safety_level?: string
  input_schema_ref?: string
  default_policy?: Record<string, unknown>
}

export interface CatalogToolCategory {
  name: string
  tools: CatalogTool[]
}

export interface ToolBundle {
  bundle_id: string
  title?: string
  description?: string
  category?: string
  tools: string[]
}

export interface BundleRecommendation {
  bundle_id: string
  confidence?: number
  rationale?: string
  suggested_additional_tools?: string[]
}

export interface RecommendToolsInput {
  name: string
  description: string
  primitive: string
  prompt: string
  repo_url?: string
  extracted_tool_ids?: string[]
}

export interface RecommendToolsResult {
  recommended_bundle_id: string
  recommended_additional_tool_ids: string[]
  rationale?: string | null
  debug?: Record<string, unknown> | null
}

export interface GitHubRepoSummary {
  id: number | string
  name: string
  full_name: string
  owner_login: string
  html_url: string
  default_branch?: string | null
  private?: boolean
  installation_type?: "oauth" | "unknown"
}

export interface GitHubConnectionState {
  status: "disconnected" | "connecting" | "connected" | "error"
  provider: "github"
  message?: string | null
  oauth_configured?: boolean
  connection_source?: "clerk" | "legacy_oauth"
}

export interface GitHubOAuthStartResponse {
  provider: "github"
  status: "not_configured" | "ready"
  authorization_url?: string | null
  /** Must match GitHub app "Authorization callback URL" (or GitHub App user callback). */
  redirect_uri?: string | null
  message?: string | null
}

export interface GitHubRepoListResponse {
  repos: GitHubRepoSummary[]
  connection: GitHubConnectionState
}

export interface GitHubOAuthPopupMessage {
  source: "github-oauth"
  status: "connected" | "error"
  session_id?: string
  github_login?: string | null
  message?: string | null
}

export interface GitHubConnectAction {
  mode: "oauth_popup"
  message: string
}

export interface RepoDiscoveredTool {
  name: string
  tool_type: string
  command?: string | null
  description?: string | null
  source_path?: string
  confidence?: number
}

export interface RepoWrappedTool {
  name: string
  tool_type: string
  command?: string | null
  description?: string | null
  source_path?: string
  wrapper_kind?: string
  safe_to_auto_expose?: boolean
  risk_level?: string
  confidence?: number
}

export interface RepoParseResult {
  repo_summary: string
  important_files: string[]
  recommended_bundle: string
  recommended_additional_tools: string[]
  draft_agent_spec: Partial<UploadAgentDraft> & Record<string, unknown>
  review_notes: string[]
  discovered_repo_tools: RepoDiscoveredTool[]
  wrapped_repo_tools: RepoWrappedTool[]
}

interface RepoRunResponse {
  run_id: string
  status: string
}

interface RepoRunStatus {
  status: string
}

export function githubRepoToImportUrl(repo: Pick<GitHubRepoSummary, "html_url">) {
  return repo.html_url
}

function buildErrorMessage(data: any, fallback: string) {
  return data?.error?.message || data?.message || fallback
}

/** Thrown when the gateway returns a non-2xx JSON error envelope (see `error.code` / `error.details`). */
export class GatewayRequestError extends Error {
  readonly code: string | undefined
  readonly details: unknown

  constructor(message: string, opts?: { code?: string; details?: unknown }) {
    super(message)
    this.name = "GatewayRequestError"
    this.code = opts?.code
    this.details = opts?.details
  }
}

async function parseJsonResponse<T>(response: Response, fallback: string): Promise<T> {
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    throw new GatewayRequestError(buildErrorMessage(data, fallback), {
      code: data?.error?.code,
      details: data?.error?.details,
    })
  }
  return data as T
}

export function createEmptyDraft(): UploadAgentDraft {
  return {
    id: "",
    version: "0.1.0",
    name: "",
    description: "",
    primitive: "transform",
    tags: [],
    credits: { name: "" },
    prompt: "",
    input_schema: {},
    output_schema: {},
    supports_memory: false,
    memory_policy: {
      mode: "last_n",
      max_messages: 10,
      max_chars: 8000,
    },
  }
}

export function draftToRecommendToolsInput(args: {
  draft: UploadAgentDraft
  repo_url?: string
  extracted_tool_ids?: string[]
}): RecommendToolsInput {
  const { draft, repo_url, extracted_tool_ids } = args
  return {
    name: draft.name.trim(),
    description: draft.description.trim(),
    primitive: draft.primitive,
    prompt: draft.prompt.trim(),
    repo_url: repo_url?.trim() || undefined,
    extracted_tool_ids: extracted_tool_ids && extracted_tool_ids.length > 0 ? extracted_tool_ids : undefined,
  }
}

export function serializeDraftToSpec(draft: UploadAgentDraft) {
  const spec: Record<string, unknown> = {
    id: draft.id.trim(),
    version: draft.version.trim(),
    name: draft.name.trim(),
    description: draft.description.trim(),
    primitive: draft.primitive,
    prompt: draft.prompt.trim(),
    input_schema: draft.input_schema || {},
    output_schema: draft.output_schema || {},
    supports_memory: draft.supports_memory,
    credits: {
      name: draft.credits.name.trim(),
      url: draft.credits.url?.trim() || undefined,
    },
  }

  if (draft.tags.length > 0) {
    spec.tags = draft.tags
  }

  if (draft.supports_memory && draft.memory_policy) {
    spec.memory_policy = draft.memory_policy
  }

  return spec
}

export function normalizeDraftFromRepo(raw: Partial<UploadAgentDraft> & Record<string, unknown>): UploadAgentDraft {
  const base = createEmptyDraft()

  const tags = Array.isArray(raw.tags)
    ? raw.tags.map((tag) => String(tag).trim()).filter(Boolean)
    : base.tags

  const credits = typeof raw.credits === "object" && raw.credits
    ? {
        name: String((raw.credits as Record<string, unknown>).name || "").trim(),
        url: String((raw.credits as Record<string, unknown>).url || "").trim() || undefined,
      }
    : base.credits

  const memoryPolicy =
    typeof raw.memory_policy === "object" && raw.memory_policy
      ? {
          mode: String((raw.memory_policy as Record<string, unknown>).mode || "last_n"),
          max_messages: Number((raw.memory_policy as Record<string, unknown>).max_messages || 10),
          max_chars: Number((raw.memory_policy as Record<string, unknown>).max_chars || 8000),
        }
      : base.memory_policy

  return {
    id: String(raw.id || base.id),
    version: String(raw.version || base.version),
    name: String(raw.name || base.name),
    description: String(raw.description || base.description),
    primitive: (raw.primitive as UploadAgentDraft["primitive"]) || base.primitive,
    tags,
    credits,
    prompt: String(raw.prompt || base.prompt),
    input_schema:
      typeof raw.input_schema === "object" && raw.input_schema ? (raw.input_schema as Record<string, unknown>) : base.input_schema,
    output_schema:
      typeof raw.output_schema === "object" && raw.output_schema ? (raw.output_schema as Record<string, unknown>) : base.output_schema,
    supports_memory: Boolean(raw.supports_memory),
    memory_policy: memoryPolicy,
  }
}

export async function fetchCatalogTools() {
  return parseJsonResponse<{ categories: CatalogToolCategory[] }>(
    await fetch(`${GATEWAY_URL}/catalog/tools`, { cache: "no-store" }),
    "Failed to load tools catalog"
  )
}

export async function fetchCatalogToolsFlat(params?: {
  q?: string
  category?: string
  execution_kind?: string
  limit?: number
}) {
  const query = new URLSearchParams()
  query.set("flat", "true")
  if (params?.q?.trim()) query.set("q", params.q.trim())
  if (params?.category?.trim()) query.set("category", params.category.trim())
  if (params?.execution_kind?.trim()) query.set("execution_kind", params.execution_kind.trim())
  if (typeof params?.limit === "number") query.set("limit", String(params.limit))

  return parseJsonResponse<{ tools: FlatCatalogTool[] }>(
    await fetch(`${GATEWAY_URL}/catalog/tools?${query.toString()}`, { cache: "no-store" }),
    "Failed to load tools catalog"
  )
}

export async function fetchCatalogBundles() {
  return parseJsonResponse<{ bundles: ToolBundle[] }>(
    await fetch(`${GATEWAY_URL}/catalog/bundles`, { cache: "no-store" }),
    "Failed to load bundle catalog"
  )
}

export async function fetchBundleRecommendation(agentIdea: string) {
  return parseJsonResponse<BundleRecommendation>(
    await fetch(`${GATEWAY_URL}/catalog/recommend`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_idea: agentIdea }),
    }),
    "Failed to get recommendations"
  )
}

export async function recommendTools(input: RecommendToolsInput) {
  const response = await parseJsonResponse<any>(
    await fetch(`${GATEWAY_URL}/catalog/recommend-tools`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
    "Failed to get tool recommendations"
  )

  return {
    recommended_bundle_id: String(response?.recommended_bundle_id || response?.bundle_id || ""),
    recommended_additional_tool_ids: Array.isArray(response?.recommended_additional_tool_ids)
      ? response.recommended_additional_tool_ids.filter((t: any) => typeof t === "string")
      : Array.isArray(response?.recommended_additional_tools)
        ? response.recommended_additional_tools.filter((t: any) => typeof t === "string")
        : Array.isArray(response?.suggested_additional_tools)
          ? response.suggested_additional_tools.filter((t: any) => typeof t === "string")
          : [],
    rationale: typeof response?.rationale === "string" ? response.rationale : null,
    debug: response?.debug && typeof response.debug === "object" ? response.debug : null,
  } satisfies RecommendToolsResult
}

export async function startGitHubOAuth(returnTo: string) {
  return parseJsonResponse<GitHubOAuthStartResponse>(
    await fetch(`${GATEWAY_URL}/github/oauth/start?${new URLSearchParams({ return_to: returnTo }).toString()}`, {
      cache: "no-store",
    }),
    "GitHub OAuth is not available yet"
  )
}

export async function fetchGitHubRepos(args?: { token?: string; sessionId?: string }) {
  const query = new URLSearchParams()
  if (args?.sessionId) query.set("session_id", args.sessionId)
  return parseJsonResponse<GitHubRepoListResponse>(
    await fetch(`${GATEWAY_URL}/github/repos${query.toString() ? `?${query.toString()}` : ""}`, {
      cache: "no-store",
      headers: args?.token ? { Authorization: `Bearer ${args.token}` } : undefined,
    }),
    "GitHub repository listing is not available yet"
  )
}

export async function getGitHubConnectAction() {
  return {
    mode: "oauth_popup",
    message: "Authorize GitHub for this app, then choose a repository from the picker.",
  } satisfies GitHubConnectAction
}

export async function connectGitHubWithPopup() {
  const returnTo = window.location.origin
  const start = await startGitHubOAuth(returnTo)
  if (start.status !== "ready" || !start.authorization_url) {
    throw new Error(start.message || "GitHub OAuth is not available yet")
  }

  const popup = window.open(
    start.authorization_url,
    "github-oauth",
    "popup=yes,width=720,height=820,resizable=yes,scrollbars=yes"
  )
  if (!popup) {
    throw new Error("GitHub popup was blocked. Allow popups for this site and try again.")
  }

  return new Promise<GitHubOAuthPopupMessage>((resolve, reject) => {
    let settled = false
    const allowedOrigin = (() => {
      try {
        return new URL(GATEWAY_URL).origin
      } catch {
        return window.location.origin
      }
    })()

    const cleanup = () => {
      window.removeEventListener("message", handleMessage)
      window.clearInterval(closePoll)
    }

    const finish = (fn: () => void) => {
      if (settled) return
      settled = true
      cleanup()
      fn()
    }

    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== allowedOrigin && event.origin !== window.location.origin) return
      const data = event.data as GitHubOAuthPopupMessage | undefined
      if (!data || data.source !== "github-oauth") return
      finish(() => {
        if (data.status === "connected" && data.session_id) {
          resolve(data)
          return
        }
        reject(new Error(data.message || "GitHub authorization failed"))
      })
    }

    const closePoll = window.setInterval(() => {
      if (!popup.closed) return
      finish(() => reject(new Error("GitHub authorization was canceled before it completed.")))
    }, 400)

    window.addEventListener("message", handleMessage)
  })
}

/**
 * Clerk bearer token for this app’s FastAPI gateway (`NEXT_PUBLIC_GATEWAY_URL`).
 *
 * Uses the **default session JWT** so backend verification matches `CLERK_JWKS_URL` /
 * `CLERK_ISSUER`. Named JWT templates (`NEXT_PUBLIC_CLERK_JWT_TEMPLATE`) usually change
 * `aud` / `iss` and cause "Invalid or expired session token" unless the gateway is
 * configured for that template. Opt in with `NEXT_PUBLIC_GATEWAY_USE_CLERK_JWT_TEMPLATE=1`.
 */
export async function getClerkSessionToken(args: {
  getToken: (options?: { template?: string }) => Promise<string | null>
}) {
  const template = (process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE || "").trim() || undefined
  const useTemplate =
    (process.env.NEXT_PUBLIC_GATEWAY_USE_CLERK_JWT_TEMPLATE || "").trim().toLowerCase() === "1" ||
    (process.env.NEXT_PUBLIC_GATEWAY_USE_CLERK_JWT_TEMPLATE || "").trim().toLowerCase() === "true"
  if (template && useTemplate) {
    try {
      return await args.getToken({ template })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      if (!message.includes("No JWT template exists with name")) {
        throw error
      }
    }
  }
  return args.getToken()
}

export async function startRepoImport(args: {
  url: string
  getToken: (options?: { template?: string }) => Promise<string | null>
}) {
  const execution_backend =
    (process.env.NEXT_PUBLIC_REPO_TO_AGENT_BACKEND || "").trim() || "internal"
  const token = await getClerkSessionToken({ getToken: args.getToken })
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  return parseJsonResponse<RepoRunResponse>(
    await fetch(`${GATEWAY_URL}/repo-to-agent/`, {
      method: "POST",
      headers,
      body: JSON.stringify({ url: args.url, execution_backend }),
    }),
    "Failed to start repository import"
  )
}

export async function fetchRepoRunStatus(runId: string) {
  return parseJsonResponse<RepoRunStatus>(
    await fetch(`${GATEWAY_URL}/runs/${encodeURIComponent(runId)}`, { cache: "no-store" }),
    "Failed to fetch import status"
  )
}

export async function fetchRepoRunResult(runId: string) {
  const response = await fetch(`${GATEWAY_URL}/runs/${encodeURIComponent(runId)}/result`, { cache: "no-store" })
  const data = await response.json().catch(() => null)
  if (response.status === 202) {
    return { pending: true as const, status: data?.status || "running" }
  }
  if (!response.ok) {
    throw new Error(buildErrorMessage(data, "Failed to fetch import result"))
  }
  return {
    pending: false as const,
    output: (data?.output || {}) as RepoParseResult,
  }
}

export async function registerAgent(spec: Record<string, unknown>, token: string) {
  return parseJsonResponse<{ ok: boolean; agent_id: string; version: string }>(
    await fetch(`${GATEWAY_URL}/agents/register`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ spec }),
    }),
    "Failed to register agent"
  )
}
