import { Suspense } from "react"
import { AgentUploadFlow } from "@/components/agent-upload/AgentUploadFlow"

export default function UploadPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-kilamanjaro" />}>
      <AgentUploadFlow />
    </Suspense>
  )
}
