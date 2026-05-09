"use client"

import { create } from "zustand"
import type {
  NativeAgentApproval,
  NativeAgentRun,
  NativeScene,
  NativeTool,
} from "@/lib/native-agent-types"
import { apiClient, isAbortError } from "@/lib/api-client"

type AgentResource = "approvals" | "runs" | "scenes" | "tools"

interface AgentWorkbenchState {
  approvals: NativeAgentApproval[]
  approvalError: string
  approvalLoading: boolean
  runs: NativeAgentRun[]
  runsError: string
  runsLoading: boolean
  scenes: NativeScene[]
  scenesError: string
  scenesLoading: boolean
  selectedSceneId: string
  tools: NativeTool[]
  toolsError: string
  toolsLoading: boolean
  abortAgentRequests: () => void
  loadApprovals: () => Promise<void>
  loadRuns: () => Promise<void>
  loadScenes: () => Promise<void>
  loadTools: () => Promise<void>
  setSelectedSceneId: (sceneId: string) => void
  invalidateAgentData: () => Promise<void>
}

const inflight = new Map<AgentResource, Promise<void>>()
const controllers = new Map<AgentResource, AbortController>()

export const useAgentWorkbenchStore = create<AgentWorkbenchState>((set, get) => ({
  approvals: [],
  approvalError: "",
  approvalLoading: false,
  runs: [],
  runsError: "",
  runsLoading: false,
  scenes: [],
  scenesError: "",
  scenesLoading: false,
  selectedSceneId: "",
  tools: [],
  toolsError: "",
  toolsLoading: false,

  abortAgentRequests: () => {
    for (const controller of controllers.values()) {
      controller.abort()
    }
    controllers.clear()
    inflight.clear()
    set({
      approvalLoading: false,
      runsLoading: false,
      scenesLoading: false,
      toolsLoading: false,
    })
  },

  setSelectedSceneId: (sceneId) => set({ selectedSceneId: sceneId }),

  loadApprovals: () =>
    dedupe("approvals", async (signal) => {
      set({ approvalError: "", approvalLoading: true })
      try {
        const data = await apiClient<NativeAgentApproval[]>("/api/agent/approvals?limit=100", {
          signal,
          retries: 1,
        })
        set({ approvals: Array.isArray(data) ? data : [] })
      } catch (error) {
        handleFetchError(error, (message) => set({ approvalError: message }))
      } finally {
        set({ approvalLoading: false })
      }
    }),

  loadRuns: () =>
    dedupe("runs", async (signal) => {
      set({ runsError: "", runsLoading: true })
      try {
        const data = await apiClient<NativeAgentRun[]>("/api/agent/runs?limit=50", {
          signal,
          retries: 1,
        })
        set({ runs: Array.isArray(data) ? data : [] })
      } catch (error) {
        handleFetchError(error, (message) => set({ runsError: message }))
      } finally {
        set({ runsLoading: false })
      }
    }),

  loadScenes: () =>
    dedupe("scenes", async (signal) => {
      set({ scenesError: "", scenesLoading: true })
      try {
        const data = await apiClient<NativeScene[]>("/api/agent/scenes", { signal, retries: 1 })
        const scenes = Array.isArray(data) ? data : []
        const selectedSceneId = get().selectedSceneId || scenes[0]?.id || ""
        set({ scenes, selectedSceneId })
      } catch (error) {
        handleFetchError(error, (message) => set({ scenesError: message }))
      } finally {
        set({ scenesLoading: false })
      }
    }),

  loadTools: () =>
    dedupe("tools", async (signal) => {
      set({ toolsError: "", toolsLoading: true })
      try {
        const data = await apiClient<NativeTool[]>("/api/agent/tools", { signal, retries: 1 })
        set({ tools: Array.isArray(data) ? data : [] })
      } catch (error) {
        handleFetchError(error, (message) => set({ toolsError: message }))
      } finally {
        set({ toolsLoading: false })
      }
    }),

  invalidateAgentData: async () => {
    await Promise.all([get().loadTools(), get().loadRuns(), get().loadApprovals()])
  },
}))

async function dedupe(
  resource: AgentResource,
  load: (signal: AbortSignal) => Promise<void>,
): Promise<void> {
  const existing = inflight.get(resource)
  if (existing) {
    return existing
  }

  const controller = new AbortController()
  controllers.set(resource, controller)
  const promise = load(controller.signal).finally(() => {
    inflight.delete(resource)
    controllers.delete(resource)
  })
  inflight.set(resource, promise)
  return promise
}

function handleFetchError(error: unknown, setError: (message: string) => void) {
  if (isAbortError(error)) {
    return
  }
  setError(error instanceof Error ? error.message : "Request failed")
}
