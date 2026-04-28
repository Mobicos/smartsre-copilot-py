"use client"

/**
 * Lightweight chat-session store backed by localStorage.
 * Keeps a synchronous in-memory mirror and notifies subscribers via custom events.
 */
import type { ChatMessage, ChatSession } from "./types"

const STORAGE_KEY = "smartsre.sessions.v1"
const EVENT = "smartsre:sessions-updated"

function read(): ChatSession[] {
  if (typeof window === "undefined") return []
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw) as ChatSession[]
  } catch {
    return []
  }
}

function write(sessions: ChatSession[]) {
  if (typeof window === "undefined") return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions))
  window.dispatchEvent(new CustomEvent(EVENT))
}

export function listSessions(): ChatSession[] {
  return read().sort((a, b) => b.updatedAt - a.updatedAt)
}

export function getSession(id: string): ChatSession | undefined {
  return read().find((s) => s.id === id)
}

export function createSession(title = "新对话"): ChatSession {
  const now = Date.now()
  const session: ChatSession = {
    id: crypto.randomUUID(),
    title,
    createdAt: now,
    updatedAt: now,
    messages: [],
  }
  const all = read()
  all.unshift(session)
  write(all)
  return session
}

export function renameSession(id: string, title: string) {
  const all = read()
  const idx = all.findIndex((s) => s.id === id)
  if (idx === -1) return
  all[idx] = { ...all[idx], title, updatedAt: Date.now() }
  write(all)
}

export function deleteSession(id: string) {
  const all = read().filter((s) => s.id !== id)
  write(all)
}

export function setMessages(id: string, messages: ChatMessage[]) {
  const all = read()
  const idx = all.findIndex((s) => s.id === id)
  if (idx === -1) return
  all[idx] = { ...all[idx], messages, updatedAt: Date.now() }
  write(all)
}

export function subscribe(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {}
  window.addEventListener(EVENT, listener)
  window.addEventListener("storage", listener)
  return () => {
    window.removeEventListener(EVENT, listener)
    window.removeEventListener("storage", listener)
  }
}
