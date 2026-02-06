export type Primitive = "transform" | "extract" | "classify"

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
  input_schema?: Record<string, any>
  output_schema?: Record<string, any>
  memory_policy?: Record<string, any> | null
}
