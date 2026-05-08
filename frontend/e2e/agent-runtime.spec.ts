import {
  expect,
  type APIRequestContext,
  type APIResponse,
  test,
} from "@playwright/test"

type JsonRecord = Record<string, unknown>

interface AgentRunResponse {
  run_id: string
  status?: string
  final_report?: string | null
}

interface WorkspaceResponse {
  id: string
}

interface SceneResponse {
  id: string
}

test.describe.configure({ mode: "serial" })

test.describe("Agent runtime production paths", () => {
  const toolName = "get_current_time"

  test.afterEach(async ({ request }) => {
    await request.patch(`/api/agent/tools/${toolName}/policy`, {
      data: {
        scope: "diagnosis",
        risk_level: "low",
        enabled: true,
        approval_required: false,
      },
    })
  })

  test("runs the Agent main path and exposes replay, events, decision state, and metrics", async ({
    page,
    request,
  }) => {
    await configureToolPolicy(request, toolName, false)
    const scene = await createScene(request, "main")

    const run = await createRun(request, scene.id, "Use the deterministic time tool and finish.")
    expect(run.run_id).toBeTruthy()
    expect(run.status).not.toBe("failed")

    const [events, replay, decisionState] = await Promise.all([
      getJson<JsonRecord[]>(await request.get(`/api/agent/runs/${run.run_id}/events`), "events"),
      getJson<JsonRecord>(
        await request.get(`/api/agent/runs/${run.run_id}/replay`),
        "replay",
      ),
      getJson<JsonRecord>(
        await request.get(`/api/agent/runs/${run.run_id}/decision-state`),
        "decision state",
      ),
    ])

    expect(events.length).toBeGreaterThan(0)
    expect(Number(readNested(replay, ["summary", "event_count"]) ?? 0)).toBeGreaterThan(0)
    expect(Number(readNested(replay, ["metrics", "decision_count"]) ?? 0)).toBeGreaterThan(0)
    expect(Number(readNested(replay, ["metrics", "tool_call_count"]) ?? 0)).toBeGreaterThan(0)
    expect(Number(readNested(decisionState, ["summary", "decision_count"]) ?? 0)).toBeGreaterThan(0)

    await page.goto(`/agent/${run.run_id}`)
    await expect(page.getByText("Replay Snapshot")).toBeVisible()
    await expect(page.getByText("Decision State")).toBeVisible()
    await expect(page.getByText("Tool Trajectory")).toBeVisible()
    await expect(page.getByText("Report", { exact: true })).toBeVisible()
  })

  test("requires approval, approves the tool call, resumes, and updates replay state", async ({
    page,
    request,
  }) => {
    await configureToolPolicy(request, toolName, true)
    const scene = await createScene(request, "approval")

    const run = await createRun(
      request,
      scene.id,
      "Use the deterministic time tool, wait for approval, and resume.",
    )
    expect(run.run_id).toBeTruthy()
    expect(run.status).toBe("waiting_approval")

    await page.goto("/agent/approvals")
    await expect(
      page.getByRole("main").getByRole("heading", { name: "Approvals" }),
    ).toBeVisible()
    await expect(page.getByText(toolName).first()).toBeVisible()
    await page.getByRole("button", { name: "Approve" }).first().click()
    await expect(page.getByRole("button", { name: "Resume" }).first()).toBeVisible()
    await page.getByRole("button", { name: "Resume" }).first().click()

    const replay = await expectEventually(async () =>
      getJson<JsonRecord>(
        await request.get(`/api/agent/runs/${run.run_id}/replay`),
        "approval replay",
      ),
    )
    const decisionState = await getJson<JsonRecord>(
      await request.get(`/api/agent/runs/${run.run_id}/decision-state`),
      "approval decision state",
    )

    expect(Number(readNested(replay, ["summary", "approval_count"]) ?? 0)).toBeGreaterThan(0)
    expect(
      Number(readNested(replay, ["summary", "approval_resume_count"]) ?? 0),
    ).toBeGreaterThan(0)
    expect(arrayLength(readNested(decisionState, ["approval_decisions"]))).toBeGreaterThan(0)
    expect(arrayLength(readNested(decisionState, ["approval_resume"]))).toBeGreaterThan(0)

    await page.goto(`/agent/${run.run_id}`)
    await expect(page.getByText("Decision State")).toBeVisible()
    await expect(page.locator("dt").filter({ hasText: /^Approvals$/ }).first()).toBeVisible()
    await expect(page.locator("dt").filter({ hasText: /^Resume$/ }).first()).toBeVisible()
  })
})

async function configureToolPolicy(
  request: APIRequestContext,
  toolName: string,
  approvalRequired: boolean,
) {
  const response = await request.patch(`/api/agent/tools/${toolName}/policy`, {
    data: {
      scope: "diagnosis",
      risk_level: approvalRequired ? "high" : "low",
      enabled: true,
      approval_required: approvalRequired,
    },
  })
  await getJson<JsonRecord>(response, "tool policy")
}

async function createScene(
  request: APIRequestContext,
  label: string,
): Promise<SceneResponse> {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`
  const workspace = await getJson<WorkspaceResponse>(
    await request.post("/api/agent/workspaces", {
      data: {
        name: `e2e-${label}-${suffix}`,
        description: "Playwright deterministic Agent runtime smoke workspace",
      },
    }),
    "workspace",
  )
  return getJson<SceneResponse>(
    await request.post("/api/agent/scenes", {
      data: {
        workspace_id: workspace.id,
        name: `e2e-${label}-${suffix}`,
        description: "Playwright deterministic Agent runtime smoke scene",
        knowledge_base_ids: [],
        tool_names: ["get_current_time"],
        agent_config: {
          decision_runtime_enabled: true,
          max_steps: 3,
          tool_timeout_seconds: 5,
          run_timeout_seconds: 30,
        },
      },
    }),
    "scene",
  )
}

async function createRun(
  request: APIRequestContext,
  sceneId: string,
  goal: string,
): Promise<AgentRunResponse> {
  return getJson<AgentRunResponse>(
    await request.post("/api/agent/runs", {
      data: {
        scene_id: sceneId,
        session_id: `e2e-${Date.now()}`,
        goal,
        success_criteria: ["A final report or approval state is persisted"],
        stop_condition: { max_steps: 3 },
        priority: "P2",
      },
    }),
    "agent run",
  )
}

async function getJson<T>(response: APIResponse, context: string): Promise<T> {
  const body = await response.json().catch(() => undefined)
  expect(response.ok(), `${context} failed with ${response.status()}: ${JSON.stringify(body)}`).toBe(
    true,
  )
  return body as T
}

async function expectEventually<T>(producer: () => Promise<T>): Promise<T> {
  let lastResult: T | undefined
  await expect
    .poll(
      async () => {
        lastResult = await producer()
        return Number(
          readNested(lastResult as JsonRecord, ["summary", "approval_resume_count"]) ?? 0,
        )
      },
      { timeout: 10_000 },
    )
    .toBeGreaterThan(0)
  return lastResult as T
}

function readNested(record: JsonRecord, path: string[]): unknown {
  return path.reduce<unknown>(
    (value, key) =>
      value && typeof value === "object" ? (value as JsonRecord)[key] : undefined,
    record,
  )
}

function arrayLength(value: unknown): number {
  return Array.isArray(value) ? value.length : 0
}
