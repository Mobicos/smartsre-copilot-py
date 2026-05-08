"use client"

import { create } from "zustand"
import type {
  NativeAgentApproval,
  NativeAgentRun,
  NativeScene,
  NativeTool,
} from "@/lib/native-agent-types"

interface AgentWorkbenchState {
  approvals: NativeAgentApproval[]
  approvalLoading: boolean
  runs: NativeAgentRun[]
  runsLoading: boolean
  scenes: NativeScene[]
  scenesLoading: boolean
  selectedSceneId: string
  tools: NativeTool[]
  toolsLoading: boolean
  loadApprovals: () => Promise<void>
  loadRuns: () => Promise<void>
  loadScenes: () => Promise<void>
  loadTools: () => Promise<void>
  setSelectedSceneId: (sceneId: string) => void
  invalidateAgentData: () => Promise<void>
}

export const useAgentWorkbenchStore = create<AgentWorkbenchState>((set, get) => ({
  approvals: [],
  approvalLoading: false,
  runs: [],
  runsLoading: false,
  scenes: [],
  scenesLoading: false,
  selectedSceneId: "",
  tools: [],
  toolsLoading: false,

  setSelectedSceneId: (sceneId) => set({ selectedSceneId: sceneId }),

  loadApprovals: async () => {
    set({ approvalLoading: true })
    try {
      const res = await fetch("/api/agent/approvals?limit=100", { cache: "no-store" })
      const data = (await res.json()) as NativeAgentApproval[] | { error?: string }
      if (!res.ok) {
        throw new Error("error" in data && data.error ? data.error : `HTTP ${res.status}`)
      }
      set({ approvals: Array.isArray(data) ? data : [] })
    } finally {
      set({ approvalLoading: false })
    }
  },

  loadRuns: async () => {
    set({ runsLoading: true })
    try {
      const res = await fetch("/api/agent/runs?limit=50", { cache: "no-store" })
      const data = (await res.json()) as { data?: NativeAgentRun[] } | NativeAgentRun[]
      set({ runs: Array.isArray(data) ? data : data.data || [] })
    } finally {
      set({ runsLoading: false })
    }
  },

  loadScenes: async () => {
    set({ scenesLoading: true })
    try {
      const res = await fetch("/api/agent/scenes", { cache: "no-store" })
      const data = (await res.json()) as NativeScene[] | { error?: string }
      if (!res.ok) {
        throw new Error("error" in data && data.error ? data.error : `HTTP ${res.status}`)
      }
      const scenes = Array.isArray(data) ? data : []
      const selectedSceneId = get().selectedSceneId || scenes[0]?.id || ""
      set({ scenes, selectedSceneId })
    } finally {
      set({ scenesLoading: false })
    }
  },

  loadTools: async () => {
    set({ toolsLoading: true })
    try {
      const res = await fetch("/api/agent/tools", { cache: "no-store" })
      const data = (await res.json()) as NativeTool[] | { error?: string }
      if (!res.ok) {
        throw new Error("error" in data && data.error ? data.error : `HTTP ${res.status}`)
      }
      set({ tools: Array.isArray(data) ? data : [] })
    } finally {
      set({ toolsLoading: false })
    }
  },

  invalidateAgentData: async () => {
    await Promise.all([get().loadTools(), get().loadRuns(), get().loadApprovals()])
  },
}))
