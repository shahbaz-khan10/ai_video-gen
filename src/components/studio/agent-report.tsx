"use client";

import { Bot, CheckCircle2, XCircle } from "lucide-react";
import type { AgentResult } from "@/types/api";

/** What the prompt agent saw and checked. Shows only what the server measured. */
export function AgentReport({ agent }: { agent: AgentResult }) {
  if (!agent.description && agent.checks.length === 0 && agent.notes.length === 0) return null;
  return (
    <div className="mt-3 rounded-lg border border-line bg-ink-900 px-3 py-2.5 text-xs leading-relaxed text-fg-muted">
      <p className="mb-1.5 flex items-center gap-1.5 font-medium text-fg">
        <Bot className="size-3.5 text-violet-soft" aria-hidden />
        Prompt agent{agent.attempts > 1 ? ` · ${agent.attempts} attempts` : ""}
      </p>
      {agent.description && (
        <p className="mb-1.5">
          <span className="text-fg-subtle">Photo understood as: </span>
          {agent.description}
        </p>
      )}
      {agent.checks.length > 0 && (
        <ul className="mb-1.5 space-y-0.5">
          {agent.checks.map((c) => (
            <li key={c.name} className="flex items-center gap-1.5">
              {c.passed ? (
                <CheckCircle2 className="size-3 text-emerald-300" aria-label="passed" />
              ) : (
                <XCircle className="size-3 text-red-300" aria-label="failed" />
              )}
              {c.name}: expected {c.expected}, found {c.found}
            </li>
          ))}
        </ul>
      )}
      {agent.notes.map((n) => (
        <p key={n} className="text-fg-subtle">
          {n}
        </p>
      ))}
    </div>
  );
}
