"use client"

export const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:4280"
const DEBUG_INGEST = "http://127.0.0.1:7244/ingest/ae01b678-64f7-4cef-bc43-0deae76993d4"

function debugLog(payload: { location: string; message: string; data?: Record<string, unknown>; hypothesisId: string; runId: string }) {
  // #region agent log
  fetch(DEBUG_INGEST, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "db76a9" },
    body: JSON.stringify({
      sessionId: "db76a9",
      timestamp: Date.now(),
      ...payload,
    }),
  }).catch(() => {})
  // #endregion agent log
}

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

function buildErrorMessage(data: any, fallback: string) {
  return data?.error?.message || data?.message || fallback
}

async function parseJsonResponse<T>(response: Response, fallback: string): Promise<T> {
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    debugLog({
      runId: "pre-fix",
      hypothesisId: "H1",
      location: "frontend/lib/agent-upload.ts:parseJsonResponse",
      message: "Gateway request failed",
      data: {
        status: response.status,
        statusText: response.statusText,
        fallback,
        errorCode: typeof data?.error?.code === "string" ? data.error.code : undefined,
        errorMessage: typeof data?.error?.message === "string" ? data.error.message : undefined,
        message: typeof data?.message === "string" ? data.message : undefined,
      },
    })
    throw new Error(buildErrorMessage(data, fallback))
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

export async function startRepoImport(url: string) {
  debugLog({
    runId: "pre-fix",
    hypothesisId: "H4",
    location: "frontend/lib/agent-upload.ts:startRepoImport",
    message: "Starting repo import",
    data: { gatewayUrl: GATEWAY_URL, repoUrlHost: (() => { try { return new URL(url).host } catch { return "invalid" } })() },
  })
  const execution_backend =
    (process.env.NEXT_PUBLIC_REPO_TO_AGENT_BACKEND || "").trim() || "internal"
  return parseJsonResponse<RepoRunResponse>(
    await fetch(`${GATEWAY_URL}/repo-to-agent/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, execution_backend }),
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
