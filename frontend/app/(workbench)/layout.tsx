import { AppSidebar } from "@/components/app-sidebar"
import { TopBar } from "@/components/top-bar"

export default function WorkbenchLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-svh w-full overflow-hidden bg-background text-foreground">
      <AppSidebar />
      <div className="flex flex-1 min-w-0 flex-col">
        <TopBar />
        <main className="flex-1 min-h-0 overflow-hidden">{children}</main>
      </div>
    </div>
  )
}
