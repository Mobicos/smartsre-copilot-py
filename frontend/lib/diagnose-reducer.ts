import type { AiopsRun, AiopsStep, AiopsToolCall } from "./types"

type Action =
  | { type: "reset"; query: string }
  | { type: "phase"; phase: AiopsRun["phase"] }
  | { type: "plan"; steps: Array<Partial<AiopsStep> & { title: string }> }
  | { type: "step:start"; index: number; title?: string }
  | { type: "step:finish"; index: number; status: AiopsStep["status"]; output?: string }
  | { type: "step:tool"; stepIndex: number; tool: AiopsToolCall }
  | { type: "report"; content: string }
  | { type: "error"; message: string }
  | { type: "done" }

export const initialRun: AiopsRun = {
  id: "",
  query: "",
  phase: "idle",
  steps: [],
  createdAt: 0,
}

export function newRun(query: string): AiopsRun {
  return {
    id: typeof crypto !== "undefined" ? crypto.randomUUID() : `${Date.now()}`,
    query,
    phase: "planning",
    steps: [],
    createdAt: Date.now(),
  }
}

export function diagnoseReducer(state: AiopsRun, action: Action): AiopsRun {
  switch (action.type) {
    case "reset":
      return newRun(action.query)
    case "phase":
      return { ...state, phase: action.phase }
    case "plan": {
      const steps: AiopsStep[] = action.steps.map((s, i) => ({
        id: s.id ?? `step-${i}`,
        index: i,
        title: s.title,
        description: s.description,
        status: s.status ?? "pending",
        toolCalls: s.toolCalls ?? [],
        output: s.output,
      }))
      return { ...state, steps, phase: "executing" }
    }
    case "step:start": {
      const steps = state.steps.map((s) =>
        s.index === action.index
          ? {
              ...s,
              status: "running" as const,
              startedAt: Date.now(),
              title: action.title ?? s.title,
            }
          : s,
      )
      // ensure step exists if backend skipped explicit plan event
      if (!steps.find((s) => s.index === action.index)) {
        steps.push({
          id: `step-${action.index}`,
          index: action.index,
          title: action.title ?? `步骤 ${action.index + 1}`,
          status: "running",
          toolCalls: [],
          startedAt: Date.now(),
        })
      }
      return { ...state, steps, phase: "executing" }
    }
    case "step:finish": {
      const steps = state.steps.map((s) =>
        s.index === action.index
          ? { ...s, status: action.status, output: action.output, finishedAt: Date.now() }
          : s,
      )
      return { ...state, steps }
    }
    case "step:tool": {
      const steps = state.steps.map((s) => {
        if (s.index !== action.stepIndex) return s
        const exists = s.toolCalls.find((t) => t.id === action.tool.id)
        const next = exists
          ? s.toolCalls.map((t) => (t.id === action.tool.id ? { ...t, ...action.tool } : t))
          : [...s.toolCalls, action.tool]
        return { ...s, toolCalls: next }
      })
      return { ...state, steps }
    }
    case "report":
      return { ...state, report: action.content, phase: "reporting" }
    case "error":
      return { ...state, phase: "error", error: action.message, finishedAt: Date.now() }
    case "done":
      return { ...state, phase: "done", finishedAt: Date.now() }
    default:
      return state
  }
}

/**
 * Best-effort interpretation of arbitrary backend SSE events into reducer actions.
 * Tolerant to multiple shapes since the backend emits LangGraph node events.
 */
export function interpretEvent(event: string, data: unknown): Action[] {
  const out: Action[] = []
  const d = (data ?? {}) as Record<string, unknown>
  const e =
    event === "message" && typeof d.type === "string"
      ? d.type.toLowerCase()
      : event.toLowerCase()

  // Plan
  if (
    e === "plan" ||
    e === "planning" ||
    (typeof d.steps === "object" && Array.isArray(d.steps)) ||
    Array.isArray(d.plan)
  ) {
    const rawSteps = (
      Array.isArray(d.steps) ? d.steps : Array.isArray(d.plan) ? d.plan : Array.isArray(data) ? data : []
    ) as unknown[]
    const steps = rawSteps.map((s) => {
      if (typeof s === "string") return { title: s }
      const o = s as Record<string, unknown>
      return {
        title: String(o.title ?? o.name ?? o.step ?? o.action ?? "步骤"),
        description:
          typeof o.description === "string"
            ? o.description
            : typeof o.detail === "string"
              ? o.detail
              : undefined,
      }
    })
    if (steps.length) out.push({ type: "plan", steps })
    return out
  }

  // Replan: same shape but signal phase
  if (e === "replan" || e === "replanning") {
    const rawSteps = (Array.isArray(d.steps) ? d.steps : []) as unknown[]
    out.push({ type: "phase", phase: "replanning" })
    if (rawSteps.length) {
      const steps = rawSteps.map((s) => {
        if (typeof s === "string") return { title: s }
        const o = s as Record<string, unknown>
        return { title: String(o.title ?? o.name ?? "步骤") }
      })
      out.push({ type: "plan", steps })
    }
    return out
  }

  // Step start / finish
  if (e === "step" || e === "execute" || e === "step_start" || e === "step:start") {
    const idx = Number(d.index ?? d.step ?? 0)
    out.push({ type: "step:start", index: idx, title: typeof d.title === "string" ? d.title : undefined })
    return out
  }
  if (e === "step_end" || e === "step:end" || e === "step_finish") {
    const idx = Number(d.index ?? d.step ?? 0)
    const status = (typeof d.status === "string" ? d.status : "succeeded") as AiopsStep["status"]
    out.push({
      type: "step:finish",
      index: idx,
      status: ["pending", "running", "succeeded", "failed", "skipped"].includes(status)
        ? status
        : "succeeded",
      output: typeof d.output === "string" ? d.output : undefined,
    })
    return out
  }

  // Tool calls
  if (e === "tool" || e === "tool_call" || e === "tool_result") {
    const stepIndex = Number(d.step ?? d.index ?? 0)
    const tool: AiopsToolCall = {
      id: String(d.id ?? d.tool_call_id ?? d.name ?? Math.random()),
      name: String(d.name ?? d.tool ?? "tool"),
      args: d.args ?? d.input,
      result: d.result ?? d.output,
      status: e === "tool_result" ? "succeeded" : "running",
    }
    out.push({ type: "step:tool", stepIndex, tool })
    return out
  }

  // Final report
  if (e === "report" || e === "final" || e === "final_report" || e === "answer") {
    const content =
      typeof data === "string"
        ? data
        : typeof d.content === "string"
          ? d.content
          : typeof d.text === "string"
            ? d.text
            : typeof d.report === "string"
              ? d.report
              : JSON.stringify(data, null, 2)
    out.push({ type: "report", content })
    return out
  }

  if (e === "error") {
    const msg = typeof data === "string" ? data : String(d.error ?? d.message ?? "诊断失败")
    out.push({ type: "error", message: msg })
    return out
  }

  if (e === "done" || e === "end" || e === "finish") {
    out.push({ type: "done" })
    return out
  }

  if (e === "complete") {
    const diagnosis = d.diagnosis
    if (diagnosis && typeof diagnosis === "object") {
      const report = (diagnosis as Record<string, unknown>).report
      if (typeof report === "string" && report) {
        out.push({ type: "report", content: report })
      }
    }
    out.push({ type: "done" })
    return out
  }

  // Generic message: try to use as token to append to current step output
  if ((e === "message" || e === "log") && typeof data === "string") {
    // ignore — handled by streaming overlay if needed
  }

  return out
}
