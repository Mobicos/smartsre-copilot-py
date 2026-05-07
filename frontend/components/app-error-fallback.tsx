"use client"

import Link from "next/link"
import { AlertTriangle, RefreshCw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

interface AppErrorFallbackProps {
  title: string
  description: string
  homeHref: string
  homeLabel: string
  error?: Error & { digest?: string }
  reset: () => void
}

export function AppErrorFallback({
  title,
  description,
  homeHref,
  homeLabel,
  error,
  reset,
}: AppErrorFallbackProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <AlertTriangle className="size-4 text-destructive" />
            {title}
          </CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            {error?.message || "Something went wrong while rendering this view."}
          </div>
          {error?.digest && (
            <p className="text-[11px] text-muted-foreground">Digest: {error.digest}</p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={reset}>
              <RefreshCw className="mr-2 size-4" />
              Retry
            </Button>
            <Button asChild variant="outline">
              <Link href={homeHref}>{homeLabel}</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
