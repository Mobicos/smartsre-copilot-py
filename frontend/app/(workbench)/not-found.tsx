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
            页面未找到
          </CardTitle>
          <CardDescription>
            此工作台页面不存在，请检查 URL 或返回。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Button asChild>
            <Link href="/agent">Agent 控制台</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/chat">返回对话</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
