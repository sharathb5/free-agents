"use client"

import { cn } from "@/lib/utils"

const STEPS = ["Source", "Details", "Tools", "Review"] as const

interface UploadFlowStepperProps {
  currentStep: number
  maxReachedStep: number
}

export function UploadFlowStepper({ currentStep, maxReachedStep }: UploadFlowStepperProps) {
  return (
    <div className="mt-8 flex items-center justify-center">
      <div className="flex flex-wrap items-center justify-center gap-3 rounded-full border border-rock-blue/15 bg-kilamanjaro/45 px-4 py-3 shadow-[0_24px_60px_-46px_rgba(159,178,205,0.42)] backdrop-blur">
        {STEPS.map((step, index) => {
          const isActive = index === currentStep
          const isComplete = index < maxReachedStep
          return (
            <div key={step} className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <div
                  className={cn(
                    "flex h-10 w-10 items-center justify-center rounded-full border text-xs font-semibold tracking-[0.18em] transition-all",
                    isActive && "border-blue-bayoux bg-blue-bayoux text-pampas shadow-[0_0_24px_rgba(73,102,119,0.45)]",
                    isComplete && !isActive && "border-olive-green/50 bg-olive-green/18 text-pampas",
                    !isActive && !isComplete && "border-rock-blue/18 bg-pampas/6 text-pampas/55"
                  )}
                >
                  {index + 1}
                </div>
                <span
                  className={cn(
                    "text-sm transition-colors",
                    isActive ? "text-pampas" : isComplete ? "text-pampas/85" : "text-pampas/50"
                  )}
                >
                  {step}
                </span>
              </div>
              {index < STEPS.length - 1 && <div className="h-px w-8 bg-rock-blue/16" />}
            </div>
          )
        })}
      </div>
    </div>
  )
}
