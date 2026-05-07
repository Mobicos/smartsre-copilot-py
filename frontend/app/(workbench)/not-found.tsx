import Link from "next/link"
import { FileQuestion } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function WorkbenchNotFound() {
  return (
    <div className="flex flex-1 items-center justify-center px-4 py-10">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileQuestion className="size-4 text-muted-foreground" />
            Page not found
          </CardTitle>
          <CardDescription>
            This workbench page does not exist. Check the URL or navigate back.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Button asChild>
            <Link href="/agent">Agent Console</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/chat">Go to chat</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
