"use client"

import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet, FieldLegend } from "@/components/ui/field"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Button } from "@/components/ui/button"
import { ShieldCheck, Sparkles } from "lucide-react"
import { useTheme } from "next-themes"
import { useEffect, useState } from "react"

export default function SettingsPage() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="mx-auto max-w-3xl px-4 py-6 md:px-6 space-y-6">
        <FieldSet>
          <FieldLegend>外观</FieldLegend>
          <FieldGroup>
            <Field>
              <FieldLabel>主题</FieldLabel>
              <FieldDescription>深色更适合凌晨值班的眼睛。</FieldDescription>
              {mounted && (
                <RadioGroup
                  value={theme ?? "system"}
                  onValueChange={(v) => setTheme(v)}
                  className="grid grid-cols-3 gap-2"
                >
                  {[
                    { v: "light", label: "浅色" },
                    { v: "dark", label: "深色" },
                    { v: "system", label: "跟随系统" },
                  ].map((o) => (
                    <Label
                      key={o.v}
                      className="flex cursor-pointer items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm hover:bg-accent has-[:checked]:border-primary has-[:checked]:bg-primary/5"
                    >
                      <RadioGroupItem value={o.v} />
                      {o.label}
                    </Label>
                  ))}
                </RadioGroup>
              )}
            </Field>
          </FieldGroup>
        </FieldSet>

        <FieldSet>
          <FieldLegend className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-primary" /> 安全与连接
          </FieldLegend>
          <div className="rounded-md border border-border bg-card p-4 text-sm leading-relaxed text-muted-foreground space-y-2">
            <p className="text-foreground">服务地址和访问凭证由系统管理员配置。</p>
            <p>
              你的浏览器永远看不到访问凭证——它只待在服务器上。如果你需要切换连接到的环境，
              请联系管理员调整后台设置。
            </p>
          </div>
        </FieldSet>

        <FieldSet>
          <FieldLegend className="flex items-center gap-2">
            <Sparkles className="size-4 text-primary" /> 关于
          </FieldLegend>
          <div className="rounded-md border border-border bg-card p-5 text-sm leading-relaxed space-y-3">
            <p className="text-pretty">
              <strong className="text-foreground">SmartSRE Copilot</strong>{" "}
              是为运维工程师设计的智能助手。
              它能读懂团队的运维资料，回答日常问题；
              也能在故障发生时陪你一起排查，并把过程透明地展示给你。
            </p>
            <p className="text-muted-foreground text-pretty">
              它不会代替你做决定，但会让你做决定时不那么孤单。
            </p>
          </div>
        </FieldSet>

        <div className="flex justify-end">
          <Button variant="outline" onClick={() => location.reload()}>
            刷新页面
          </Button>
        </div>
      </div>
    </div>
  )
}
