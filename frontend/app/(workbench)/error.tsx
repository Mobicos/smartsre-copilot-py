"use client"

import { AppErrorFallback } from "@/components/app-error-fallback"

export default function WorkbenchError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <AppErrorFallback
      title="工作台错误"
      description="工作台面板渲染失败，其余功能仍可正常使用。"
      homeHref="/chat"
      homeLabel="返回对话"
      error={error}
      reset={reset}
    />
  )
}
