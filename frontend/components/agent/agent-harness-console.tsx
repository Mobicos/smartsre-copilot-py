"use client"

import { useCallback, useEffect, useState } from "react"
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Play,
  Square,
} from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Markdown } from "@/components/markdown"
import { AgentEventTimeline } from "./agent-event-timeline"
import { useAgentWorkbenchStore } from "@/lib/agent-workbench-store"
import { useEventStream } from "@/lib/use-event-stream"
import { tryParseJSON } from "@/lib/sse"
import type {
  NativeAgentEvent,
  NativeScene,
  NativeWorkspace,
} from "@/lib/native-agent-types"
import { cn } from "@/lib/utils"

const DEFAULT_GOAL = "Investigate the current production incident, identify likely root cause, and produce an SRE-ready report."

type RunPhase = "idle" | "running" | "done" | "error"

interface RunState {
  phase: RunPhase
  runId: string | null
  report: string | null
  error: string | null
  events: NativeAgentEvent[]
}

const initialRunState: RunState = {
  phase: "idle",
  runId: null,
  report: null,
  error: null,
  events: [],
}

export function AgentHarnessConsole() {
  const scenes = useAgentWorkbenchStore((state) => state.scenes)
  const selectedSceneId = useAgentWorkbenchStore((state) => state.selectedSceneId)
  const setSelectedSceneId = useAgentWorkbenchStore((state) => state.setSelectedSceneId)
  const loadStoreScenes = useAgentWorkbenchStore((state) => state.loadScenes)
  const invalidateAgentData = useAgentWorkbenchStore((state) => state.invalidateAgentData)
  const [goal, setGoal] = useState(DEFAULT_GOAL)
  const [runState, setRunState] = useState<RunState>(initialRunState)
  const [loading, setLoading] = useState(true)
  const [showConfig, setShowConfig] = useState(false)
  const { start, abort, isRunning } = useEventStream()

  const loadScenes = useCallback(async () => {
    setLoading(true)
    try {
      const [workspaceData, scenesData] = await Promise.all([
        fetchJson<NativeWorkspace[]>("/api/agent/workspaces"),
        fetchJson<NativeScene[]>("/api/agent/scenes"),
      ])

      let nextScenes = scenesData
      if (nextScenes.length === 0 && workspaceData.length > 0) {
        const createdScene = await fetchJson<NativeScene>("/api/agent/scenes", {
          method: "POST",
          body: JSON.stringify({
            workspace_id: workspaceData[0].id,
            name: "Default",
            description: "Default diagnosis scene",
          }),
        })
        nextScenes = [createdScene]
      }

      setSelectedSceneId(nextScenes[0]?.id || "")
      await loadStoreScenes()
    } catch (err) {
      toast.error("Failed to load scenes")
    } finally {
      setLoading(false)
    }
  }, [loadStoreScenes, setSelectedSceneId])

  useEffect(() => {
    void loadScenes()
  }, [loadScenes])

  function runDiagnosis() {
    const sceneId = selectedSceneId
    const trimmedGoal = goal.trim()
    if (!sceneId || !trimmedGoal || isRunning()) return

    setRunState({
      phase: "running",
      runId: null,
      report: null,
      error: null,
      events: [],
    })

    void start(
      "/api/agent/runs/stream",
      {
        scene_id: sceneId,
        session_id: `session-${Date.now()}`,
        goal: trimmedGoal,
        success_criteria: [
          "Collect authoritative tool or knowledge evidence before claiming a root cause.",
          "Produce a bounded handoff when evidence is insufficient.",
        ],
        stop_condition: {
          max_steps: 5,
          max_minutes: 2,
          confidence_threshold: 0.75,
        },
        priority: "P1",
      },
      {
        onEvent: (_event, data) => {
          const parsed = tryParseJSON(data)
          if (parsed && typeof parsed === "object") {
            const agentEvent = parsed as NativeAgentEvent
            setRunState((prev) => {
              const newEvents = [...prev.events, agentEvent]
              const newState: RunState = {
                ...prev,
                events: newEvents,
                runId: agentEvent.run_id || prev.runId,
              }

              if (
                agentEvent.type === "complete" ||
                agentEvent.type === "handoff" ||
                agentEvent.type === "approval_required"
              ) {
                newState.phase = "done"
                void invalidateAgentData()
                if (typeof agentEvent.final_report === "string") {
                  newState.report = agentEvent.final_report
                } else if (agentEvent.type === "approval_required") {
                  newState.report = "Tool execution is waiting for human approval."
                }
              } else if (agentEvent.type === "final_report") {
                const payload = agentEvent.payload as Record<string, unknown> | undefined
                if (payload && typeof payload.report === "string") {
                  newState.report = payload.report
                }
              } else if (agentEvent.type === "error") {
                newState.phase = "error"
                newState.error = agentEvent.message || "Diagnosis failed"
                void invalidateAgentData()
              }

              return newState
            })
          }
        },
        onError: (err) => {
          setRunState((prev) => ({
            ...prev,
            phase: "error",
            error: (err as Error)?.message ?? "Diagnosis failed",
          }))
        },
        onDone: () => {
          setRunState((prev) => {
            if (prev.phase === "running") {
              return { ...prev, phase: "done" }
            }
            return prev
          })
        },
      },
    )
  }

  function stopDiagnosis() {
    abort()
    setRunState((prev) => ({
      ...prev,
      phase: "error",
      error: "Stopped by user",
    }))
  }

  function resetRun() {
    abort()
    setRunState(initialRunState)
  }

  const phaseLabel: Record<RunPhase, string> = {
    idle: "Ready",
    running: "Running",
    done: "Done",
    error: "Failed",
  }

  const phaseClass: Record<RunPhase, string> = {
    idle: "bg-muted text-muted-foreground border-border",
    running: "bg-primary/15 text-primary border-primary/30",
    done: "bg-success/15 text-success border-success/30",
    error: "bg-destructive/15 text-destructive border-destructive/30",
  }

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-4xl px-4 py-6 md:px-6">
        {/* Goal Input */}
        <div className="mb-4">
          <Textarea
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            disabled={isRunning()}
            className="min-h-24 text-base"
            placeholder="Describe the incident or problem to investigate..."
          />
        </div>

        {/* Action Bar */}
        <div className="mb-4 flex items-center gap-3">
          {isRunning() ? (
            <Button variant="destructive" onClick={stopDiagnosis}>
              <Square className="size-4 fill-current" />
              Stop
            </Button>
          ) : (
            <>
              <Button
                onClick={runDiagnosis}
                disabled={!selectedSceneId || !goal.trim() || loading}
              >
                <Play className="size-4" />
                Run
              </Button>
              {runState.phase !== "idle" && (
                <Button variant="outline" size="sm" onClick={resetRun}>
                  Reset
                </Button>
              )}
            </>
          )}

          {/* Status */}
          {runState.phase !== "idle" && (
            <div
              className={cn(
                "flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm",
                phaseClass[runState.phase],
              )}
            >
              {runState.phase === "running" && (
                <Loader2 className="size-3 animate-spin" />
              )}
              {runState.phase === "done" && <CheckCircle2 className="size-3" />}
              {runState.phase === "error" && <AlertTriangle className="size-3" />}
              <span>{phaseLabel[runState.phase]}</span>
              {runState.runId && (
                <span className="font-mono text-xs text-muted-foreground">
                  {runState.runId.slice(0, 8)}
                </span>
              )}
            </div>
          )}

          {/* Config Toggle */}
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={() => setShowConfig(!showConfig)}
          >
            {showConfig ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
            Config
          </Button>
        </div>

        {/* Config Panel (collapsed by default) */}
        {showConfig && (
          <div className="mb-4 rounded-md border border-border p-3 text-sm">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1">
                <span className="text-xs text-muted-foreground">Scene</span>
                <select
                  value={selectedSceneId}
                  onChange={(event) => setSelectedSceneId(event.target.value)}
                  disabled={loading || isRunning()}
                  className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm"
                >
                  {scenes.map((scene) => (
                    <option key={scene.id} value={scene.id}>
                      {scene.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        )}

        {/* Error */}
        {runState.error && (
          <div className="mb-4 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>{runState.error}</span>
          </div>
        )}

        {/* Events Timeline */}
        {runState.events.length > 0 && (
          <div className="mb-4">
            <AgentEventTimeline
              events={runState.events}
              isRunning={runState.phase === "running"}
            />
          </div>
        )}

        {/* Final Report */}
        {runState.report && (
          <div className="rounded-lg border border-border bg-card p-4">
            <Markdown content={runState.report} />
          </div>
        )}
      </div>
    </div>
  )
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set("content-type", "application/json")
  const res = await fetch(url, {
    ...init,
    headers,
    cache: "no-store",
  })
  const json = (await res.json()) as T | { error?: string; detail?: string }
  if (!res.ok) {
    const error = json as { error?: string; detail?: string }
    throw new Error(error.error || error.detail || `HTTP ${res.status}`)
  }
  return json as T
}
