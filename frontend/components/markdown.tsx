"use client"

/**
 * Tiny dependency-free markdown renderer tuned for chat output.
 * Supports: headings, bold/italic, inline code, fenced code blocks,
 * unordered/ordered lists, links, blockquotes, horizontal rules.
 */
import { cn } from "@/lib/utils"

function escapeHtml(s: string) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}

function renderInline(text: string): string {
  let out = escapeHtml(text)
  // code
  out = out.replace(
    /`([^`]+)`/g,
    '<code class="rounded bg-muted px-1 py-0.5 text-[0.85em] font-mono">$1</code>',
  )
  // links
  out = out.replace(
    /\[([^\]]+)\]\(([^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noreferrer noopener" class="text-primary underline-offset-2 hover:underline">$1</a>',
  )
  // bold
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
  // italic
  out = out.replace(/(^|\W)\*([^*\n]+)\*/g, "$1<em>$2</em>")
  return out
}

function renderMarkdownToHTML(md: string): string {
  const lines = md.replace(/\r\n/g, "\n").split("\n")
  const out: string[] = []
  let inCode = false
  let codeLang = ""
  let codeBuf: string[] = []
  let listType: "ul" | "ol" | null = null
  let inBlockquote = false

  const closeList = () => {
    if (listType) {
      out.push(`</${listType}>`)
      listType = null
    }
  }
  const closeBlockquote = () => {
    if (inBlockquote) {
      out.push("</blockquote>")
      inBlockquote = false
    }
  }

  for (const raw of lines) {
    const line = raw

    // fenced code
    const fence = line.match(/^```(\w+)?\s*$/)
    if (fence) {
      if (inCode) {
        out.push(
          `<pre class="my-2 overflow-x-auto rounded-md border border-border bg-muted/60 p-3 text-[12.5px] leading-relaxed font-mono"><code data-lang="${escapeHtml(
            codeLang,
          )}">${escapeHtml(codeBuf.join("\n"))}</code></pre>`,
        )
        codeBuf = []
        codeLang = ""
        inCode = false
      } else {
        closeList()
        closeBlockquote()
        inCode = true
        codeLang = fence[1] ?? ""
      }
      continue
    }
    if (inCode) {
      codeBuf.push(line)
      continue
    }

    if (!line.trim()) {
      closeList()
      closeBlockquote()
      continue
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/)
    if (heading) {
      closeList()
      closeBlockquote()
      const lvl = heading[1].length
      const sizes = ["text-xl", "text-lg", "text-base", "text-sm", "text-sm", "text-xs"]
      out.push(
        `<h${lvl} class="mt-3 mb-2 font-semibold ${sizes[lvl - 1]}">${renderInline(heading[2])}</h${lvl}>`,
      )
      continue
    }

    if (/^---+$/.test(line.trim())) {
      closeList()
      closeBlockquote()
      out.push('<hr class="my-3 border-border" />')
      continue
    }

    const bq = line.match(/^>\s?(.*)$/)
    if (bq) {
      closeList()
      if (!inBlockquote) {
        out.push(
          '<blockquote class="my-2 border-l-2 border-primary/60 bg-muted/40 pl-3 py-1 text-muted-foreground">',
        )
        inBlockquote = true
      }
      out.push(`<p>${renderInline(bq[1])}</p>`)
      continue
    } else {
      closeBlockquote()
    }

    const ol = line.match(/^\s*\d+\.\s+(.*)$/)
    const ul = line.match(/^\s*[-*+]\s+(.*)$/)
    if (ol) {
      if (listType !== "ol") {
        closeList()
        out.push('<ol class="my-2 list-decimal pl-5 space-y-1">')
        listType = "ol"
      }
      out.push(`<li>${renderInline(ol[1])}</li>`)
      continue
    }
    if (ul) {
      if (listType !== "ul") {
        closeList()
        out.push('<ul class="my-2 list-disc pl-5 space-y-1">')
        listType = "ul"
      }
      out.push(`<li>${renderInline(ul[1])}</li>`)
      continue
    }

    closeList()
    out.push(`<p class="my-1.5">${renderInline(line)}</p>`)
  }

  closeList()
  closeBlockquote()
  if (inCode) {
    out.push(
      `<pre class="my-2 overflow-x-auto rounded-md border border-border bg-muted/60 p-3 text-[12.5px] font-mono"><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`,
    )
  }
  return out.join("\n")
}

export function Markdown({ content, className }: { content: string; className?: string }) {
  const html = renderMarkdownToHTML(content)
  return (
    <div
      className={cn(
        "prose-like text-sm leading-relaxed [&_p]:break-words [&_p]:text-pretty",
        className,
      )}
      // Markdown HTML is generated locally from raw text and escaped; safe to inject.
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
