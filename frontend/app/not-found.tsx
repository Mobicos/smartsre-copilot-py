import Link from "next/link"
import { FileQuestion } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileQuestion className="size-4 text-muted-foreground" />
            页面未找到
          </CardTitle>
          <CardDescription>
            您访问的页面不存在或已被移动。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link href="/chat">返回对话</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
