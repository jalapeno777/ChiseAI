import type { Plugin } from "@opencode-ai/plugin"
import { mkdir, appendFile } from "node:fs/promises"
import { join } from "node:path"

const MAX_TEXT = 500

function compact(value: unknown, limit = MAX_TEXT): string {
  try {
    const text = typeof value === "string" ? value : JSON.stringify(value)
    return text.length > limit ? text.slice(0, limit) + " …[truncated]" : text
  } catch {
    return String(value)
  }
}

function interesting(event: any) {
  return [
    "session.error",
    "session.idle",
    "session.compacted",
    "tool.execute.before",
    "tool.execute.after",
    "permission.asked",
    "permission.replied",
    "command.executed",
    "todo.updated",
    "file.edited",
    "lsp.client.diagnostics",
  ].includes(event?.type)
}

function normalize(event: any) {
  const base = {
    ts: new Date().toISOString(),
    type: event?.type,
  }

  switch (event?.type) {
    case "session.error":
      return {
        ...base,
        sessionID: event.properties?.sessionID,
        error: compact(event.properties?.error ?? event.properties),
      }

    case "permission.asked":
    case "permission.replied":
      return {
        ...base,
        sessionID: event.properties?.sessionID,
        tool: event.properties?.tool,
        value: compact(event.properties),
      }

    case "tool.execute.before":
    case "tool.execute.after":
      return {
        ...base,
        sessionID: event.properties?.sessionID,
        tool: event.properties?.tool,
        args: compact(event.properties?.args),
        result: compact(event.properties?.result),
        error: compact(event.properties?.error),
      }

    case "file.edited":
      return {
        ...base,
        sessionID: event.properties?.sessionID,
        file: event.properties?.file,
      }

    case "lsp.client.diagnostics":
      return {
        ...base,
        sessionID: event.properties?.sessionID,
        diagnostics: compact(event.properties?.diagnostics),
      }

    case "command.executed":
      return {
        ...base,
        sessionID: event.properties?.sessionID,
        command: compact(event.properties?.command),
      }

    case "todo.updated":
      return {
        ...base,
        sessionID: event.properties?.sessionID,
        todo: compact(event.properties?.todo ?? event.properties),
      }

    case "session.idle":
    case "session.compacted":
      return {
        ...base,
        sessionID: event.properties?.sessionID,
        value: compact(event.properties),
      }

    default:
      return {
        ...base,
        value: compact(event.properties),
      }
  }
}

export const SelfAuditTelemetry: Plugin = async ({ directory }) => {
  const dataDir = join(directory, ".opencode", "data", "self-audit")
  const eventsPath = join(dataDir, "events.jsonl")

  await mkdir(dataDir, { recursive: true })

  return {
    event: async ({ event }) => {
      if (!interesting(event)) return
      const record = normalize(event)
      await appendFile(eventsPath, JSON.stringify(record) + "\n")
    },
  }
}
