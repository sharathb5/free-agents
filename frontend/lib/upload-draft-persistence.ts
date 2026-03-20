export type UploadDraftPersistedStateV1 = {
  version: 1
  updated_at: number
  path: "build" | "github" | null
  step: number
  max_reached_step: number
  repo_url: string
  repo_summary: string
  draft: any
  selections: {
    selected_bundle_id: string
    selected_tool_ids: string[]
    recommended_bundle_id: string
    recommended_tool_ids: string[]
    extracted_tool_ids: string[]
    user_edited_bundle: boolean
    user_edited_tools: boolean
  }
}

const STORAGE_KEY = "agent_upload_v1"

function isBrowser() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined"
}

export function loadUploadDraftState(): UploadDraftPersistedStateV1 | null {
  if (!isBrowser()) return null
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") return null
    if (parsed.version !== 1) return null
    return parsed as UploadDraftPersistedStateV1
  } catch {
    return null
  }
}

export function saveUploadDraftState(state: UploadDraftPersistedStateV1) {
  if (!isBrowser()) return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // ignore quota/serialization failures
  }
}

export function clearUploadDraftState() {
  if (!isBrowser()) return
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}

