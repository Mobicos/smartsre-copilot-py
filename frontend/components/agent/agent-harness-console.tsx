"use client"

import { useCallback, useEffect, useState, useTransition } from "react"
import { Bot, Boxes, CheckCircle2, Loader2, Play, RefreshCw, Wrench } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Markdown } from "@/components/markdown"
import type {
  NativeAgentEvent,
  NativeAgentRun,
  NativeScene,
  NativeTool,
  NativeWorkspace,
} from "@/lib/native-agent-types"
import { cn } from "@/lib/utils"

const DEFAULT_GOAL =
  "Investigate the current production incident, identify likely root cause, and produce an SRE-ready report."

export function AgentHarnessConsole() {
  const [workspaces, setWorkspaces] = useState<NativeWorkspace[]>([])
  const [scenes, setScenes] = useState<NativeScene[]>([])
  const [tools, setTools] = useState<NativeTool[]>([])
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("")
  const [selectedSceneId, setSelectedSceneId] = useState("")
  const [sessionId, setSessionId] = useState("agent-default")
  const [goal, setGoal] = useState(DEFAULT_GOAL)
  const [run, setRun] = useState<NativeAgentRun | null>(null)
  const [events, setEvents] = useState<NativeAgentEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [isPending, startTransition] = useTransition()

  const loadHarness = useCallback(async (workspaceIdHint = "", sceneIdHint = "") => {
    setLoading(true)
    try {
      const [workspaceData, toolData] = await Promise.all([
        fetchJson<NativeWorkspace[]>("/api/agent/workspaces"),
        fetchJson<NativeTool[]>("/api/agent/tools"),
      ])
      let nextWorkspaces = workspaceData
      if (nextWorkspaces.length === 0) {
        const created = await fetchJson<NativeWorkspace>("/api/agent/workspaces", {
          method: "POST",
          body: JSON.stringify({
            name: "Default SRE Workspace",
            description: "Created by the frontend Native Agent harness.",
          }),
        })
        nextWorkspaces = [created]
      }

      const workspaceId = workspaceIdHint || nextWorkspaces[0]?.id || ""
      let nextScenes = workspaceId
        ? await fetchJson<NativeScene[]>(
            `/api/agent/scenes?workspace_id=${encodeURIComponent(workspaceId)}`,
          )
        : []
      if (workspaceId && nextScenes.length === 0) {
        const createdScene = await fetchJson<NativeScene>("/api/agent/scenes", {
          method: "POST",
          body: JSON.stringify({
            workspace_id: workspaceId,
            name: "Default SRE Diagnosis",
            description: "Default scene for Native Agent diagnosis.",
            knowledge_base_ids: [],
            tool_names: toolData.map((tool) => tool.name),
            agent_config: { mode: "native-harness" },
          }),
        })
        nextScenes = [createdScene]
      }

      setWorkspaces(nextWorkspaces)
      setTools(toolData)
      setSelectedWorkspaceId(workspaceId)
      setScenes(nextScenes)
      setSelectedSceneId(sceneIdHint || nextScenes[0]?.id || "")
    } catch (err) {
      toast.error((err as Error).message || "Failed to load Native Agent harness")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadHarness()
  }, [loadHarness])

  async function refreshHarness() {
    await loadHarness(selectedWorkspaceId, selectedSceneId)
  }

  async function onWorkspaceChange(workspaceId: string) {
    setSelectedWorkspaceId(workspaceId)
    setSelectedSceneId("")
    try {
      const nextScenes = await fetchJson<NativeScene[]>(
        `/api/agent/scenes?workspace_id=${encodeURIComponent(workspaceId)}`,
      )
      setScenes(nextScenes)
      setSelectedSceneId(nextScenes[0]?.id || "")
    } catch (err) {
      toast.error((err as Error).message || "Failed to load scenes")
    }
  }

  function runAgent() {
    const sceneId = selectedSceneId
    const trimmedGoal = goal.trim()
    if (!sceneId || !trimmedGoal) return

    startTransition(() => {
      void (async () => {
        setRun(null)
        setEvents([])
        try {
          const nextRun = await fetchJson<NativeAgentRun>("/api/agent/runs", {
            method: "POST",
            body: JSON.stringify({
              scene_id: sceneId,
              session_id: sessionId.trim() || "agent-default",
              goal: trimmedGoal,
            }),
          })
          setRun(nextRun)
          if (nextRun.run_id) {
            const nextEvents = await fetchJson<NativeAgentEvent[]>(
              `/api/agent/runs/${encodeURIComponent(nextRun.run_id)}/events`,
            )
            setEvents(nextEvents)
          }
        } catch (err) {
          toast.error((err as Error).message || "Native Agent run failed")
        }
      })()
    })
  }

  const selectedScene = scenes.find((scene) => scene.id === selectedSceneId)

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto grid max-w-6xl gap-4 px-4 py-6 md:px-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="size-5 text-primary" />
              Native Agent Harness
            </CardTitle>
            <CardDescription>
              Run the latest backend AgentRuntime through scenes, tools, persisted runs, and
              event history.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1.5 text-sm">
                <span className="font-medium">Workspace</span>
                <select
                  value={selectedWorkspaceId}
                  onChange={(event) => void onWorkspaceChange(event.target.value)}
                  disabled={loading || isPending}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {workspaces.map((workspace) => (
                    <option key={workspace.id} value={workspace.id}>
                      {workspace.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-1.5 text-sm">
                <span className="font-medium">Scene</span>
                <select
                  value={selectedSceneId}
                  onChange={(event) => setSelectedSceneId(event.target.value)}
                  disabled={loading || isPending}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {scenes.map((scene) => (
                    <option key={scene.id} value={scene.id}>
                      {scene.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="space-y-1.5 text-sm">
              <span className="font-medium">Session ID</span>
              <Input
                value={sessionId}
                onChange={(event) => setSessionId(event.target.value)}
                disabled={isPending}
              />
            </label>

            <label className="space-y-1.5 text-sm">
              <span className="font-medium">Goal</span>
              <Textarea
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                disabled={isPending}
                className="min-h-32"
              />
            </label>

            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={runAgent} disabled={!selectedSceneId || !goal.trim() || isPending}>
                {isPending ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
                Run Agent
              </Button>
              <Button variant="outline" onClick={() => void refreshHarness()} disabled={loading || isPending}>
                <RefreshCw className={cn("size-4", loading && "animate-spin")} />
                Refresh Harness
              </Button>
              {selectedScene && (
                <span className="text-xs text-muted-foreground">
                  Scene: <span className="font-mono">{selectedScene.id}</span>
                </span>
              )}
            </div>

            {run && (
              <div className="rounded-lg border border-border bg-muted/30 p-4">
                <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
                  <CheckCircle2 className="size-4 text-success" />
                  <span className="font-medium">Run {run.status || "completed"}</span>
                  <span className="rounded bg-background px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
                    {run.run_id}
                  </span>
                </div>
                {run.final_report ? (
                  <Markdown content={run.final_report} />
                ) : (
                  <p className="text-sm text-muted-foreground">No final report returned.</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Wrench className="size-4 text-primary" />
                Tools
              </CardTitle>
              <CardDescription>{tools.length} tools exposed by the backend catalog.</CardDescription>
            </CardHeader>
            <CardContent>
              {tools.length === 0 ? (
                <p className="text-sm text-muted-foreground">No tools loaded yet.</p>
              ) : (
                <ul className="space-y-2">
                  {tools.map((tool) => (
                    <li key={tool.name} className="rounded-md border border-border p-2 text-sm">
                      <div className="font-medium">{tool.name}</div>
                      {tool.description && (
                        <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                          {tool.description}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Boxes className="size-4 text-primary" />
                Run Events
              </CardTitle>
              <CardDescription>Persisted event history from `/api/agent/runs/*/events`.</CardDescription>
            </CardHeader>
            <CardContent>
              {events.length === 0 ? (
                <p className="text-sm text-muted-foreground">Run an agent to load events.</p>
              ) : (
                <ol className="space-y-2">
                  {events.map((event, index) => (
                    <li key={`${event.id ?? index}`} className="rounded-md border border-border p-2 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium">{event.type || "event"}</span>
                        {event.created_at && (
                          <span className="text-muted-foreground">{event.created_at}</span>
                        )}
                      </div>
                      {event.message && (
                        <p className="mt-1 text-muted-foreground">{event.message}</p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </div>
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
