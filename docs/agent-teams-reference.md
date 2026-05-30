# Agent Teams — Master Reference

Source: https://code.claude.com/docs/en/agent-teams  
Last updated: 2026-05-30

---

## What Are Agent Teams?

Agent teams coordinate multiple Claude Code instances working together. One session acts as the **team lead** — it creates the team, spawns teammates, and coordinates work. **Teammates** are fully independent Claude Code instances that communicate directly with each other (not just through the lead).

> **Status:** Experimental, disabled by default. Requires Claude Code v2.1.32+.

**Enable:**
```json
// settings.json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

---

## Agent Teams vs. Subagents — When to Use Which

| Dimension | Subagents | Agent Teams |
|---|---|---|
| Context | Own context window; results return to caller | Own context window; fully independent |
| Communication | Report back to main agent only | Teammates message each other directly |
| Coordination | Main agent manages all work | Shared task list with self-coordination |
| Best for | Focused tasks where only the result matters | Complex work needing discussion + collaboration |
| Token cost | Lower — results summarized back | Higher — each teammate is a separate Claude instance |

**Use subagents when:** workers only need to report results back. No inter-agent coordination needed.

**Use agent teams when:** workers need to share findings, challenge each other, or self-coordinate across a shared task list.

---

## Best Use Cases

Agent teams shine when **parallel exploration adds real value** and teammates can work **independently**:

1. **Research & review** — Multiple teammates investigate different aspects simultaneously, then challenge each other's findings
2. **New modules/features** — Each teammate owns a separate piece; no shared-file conflicts
3. **Debugging with competing hypotheses** — Teammates test different root-cause theories in parallel and converge faster
4. **Cross-layer coordination** — Changes spanning frontend, backend, and tests, each owned by a different teammate

**Avoid agent teams for:** sequential tasks, same-file edits, or work with many inter-step dependencies. A single session or subagents are more efficient there.

---

## Architecture

```
Team Lead (main session)
  ├── Task List (shared, file-locked)
  ├── Mailbox (messaging between agents)
  ├── Teammate A — own context window
  ├── Teammate B — own context window
  └── Teammate C — own context window
```

| Component | Role |
|---|---|
| Team lead | Creates team, spawns teammates, coordinates work |
| Teammates | Separate Claude Code instances working on assigned tasks |
| Task list | Shared work items; teammates claim + complete |
| Mailbox | Direct agent-to-agent messaging system |

**Storage locations:**
- Team config: `~/.claude/teams/{team-name}/config.json`
- Task list: `~/.claude/tasks/{team-name}/`

> Do not hand-edit `config.json` — it's overwritten on every state update.

---

## Starting a Team

Just describe the task and structure in natural language. Claude handles the rest:

```
Create an agent team to explore this CLI tool from different angles:
one teammate on UX, one on technical architecture, one playing devil's advocate.
```

Claude will:
1. Create the team with a shared task list
2. Spawn teammates per your instructions
3. Have them work and communicate
4. Synthesize findings
5. Clean up the team when done

**To specify teammates or models:**
```
Create a team with 4 teammates to refactor these modules in parallel.
Use Sonnet for each teammate.
```

Note: teammates don't inherit the lead's `/model` by default. Set **Default teammate model** in `/config`, or use "Default (leader's model)" to follow the lead.

---

## Display Modes

| Mode | How it works | Requires |
|---|---|---|
| `in-process` (default) | All teammates run in your main terminal; Shift+Down to cycle | Nothing |
| `tmux` / split panes | Each teammate gets its own pane; all visible at once | tmux or iTerm2 |

**Override in settings:**
```json
{ "teammateMode": "in-process" }
```

**Override for one session:**
```bash
claude --teammate-mode in-process
```

**Keyboard shortcuts (in-process mode):**
- `Shift+Down` — cycle through teammates
- `Enter` — view a teammate's session
- `Escape` — interrupt teammate's current turn
- `Ctrl+T` — toggle task list

---

## Controlling the Team

### Talk to teammates directly
In-process: use Shift+Down to cycle to the teammate, then type.
Split-pane: click into the teammate's pane.

### Plan approval (for risky tasks)
```
Spawn an architect teammate to refactor auth. Require plan approval before changes.
```
Lead reviews plans, approves or rejects with feedback. Teammate stays in read-only plan mode until approved.

### Task assignment
- **Lead assigns**: tell the lead which task to give to which teammate
- **Self-claim**: teammates pick up the next unassigned, unblocked task after finishing one

File locking prevents race conditions when multiple teammates try to claim the same task.

### Shutting down teammates
```
Ask the researcher teammate to shut down
```
Teammate can approve (graceful exit) or reject with explanation.

### Cleaning up the team
```
Clean up the team
```
Always use the lead to clean up — teammate cleanup can leave resources in an inconsistent state. Shut down all active teammates first.

---

## Context and Communication

- Each teammate loads project context fresh: CLAUDE.md, MCP servers, skills
- The lead's conversation history does **not** carry over to teammates
- Teammate messages are delivered automatically — lead doesn't need to poll
- Idle notifications sent automatically when a teammate stops
- Any teammate can message any other by name (lead assigns names at spawn)

**To get predictable names:** tell the lead what to call each teammate in the spawn prompt.

---

## Using Subagent Definitions for Teammates

You can reference a subagent type when spawning a teammate to reuse role definitions:

```
Spawn a teammate using the security-reviewer agent type to audit the auth module.
```

The teammate honors the definition's `tools` allowlist and `model`. The definition body is appended to the teammate's system prompt (not replacing it). Team coordination tools (`SendMessage`, task tools) are always available even when `tools` restricts others.

> Note: `skills` and `mcpServers` frontmatter fields in subagent definitions are not applied when running as a teammate — those come from project/user settings.

---

## Permissions

- Teammates start with the lead's permission settings
- If lead uses `--dangerously-skip-permissions`, all teammates do too
- Can change individual teammate modes after spawning
- Cannot set per-teammate modes at spawn time

---

## Hooks for Quality Gates

| Hook | Trigger | Exit 2 = |
|---|---|---|
| `TeammateIdle` | Teammate about to go idle | Send feedback, keep working |
| `TaskCreated` | Task being created | Prevent creation + send feedback |
| `TaskCompleted` | Task being marked complete | Prevent completion + send feedback |

---

## Best Practices

### 1. Give teammates enough context in the spawn prompt
Teammates don't inherit the lead's conversation history. Be explicit:
```
Spawn a security reviewer with: "Review src/auth/ for vulnerabilities.
Focus on token handling, session management, and input validation.
App uses JWT tokens in httpOnly cookies. Rate findings by severity."
```

### 2. Team size: start with 3–5 teammates
- Token costs scale linearly with teammates
- Coordination overhead increases with size
- Diminishing returns beyond ~5
- Target **5–6 tasks per teammate** to keep everyone productive

### 3. Size tasks appropriately
- Too small → coordination overhead exceeds benefit
- Too large → teammate works too long without check-ins, risk of wasted effort
- Just right → self-contained unit with a clear deliverable (one function, one test file, one review)

### 4. Prevent file conflicts
Two teammates editing the same file = overwrites. Partition work so each teammate owns different files.

### 5. Tell the lead to wait if it jumps ahead
```
Wait for your teammates to complete their tasks before proceeding
```

### 6. Start with research/review tasks
If new to agent teams, start with tasks that have clear boundaries and don't write code (PR review, library research, bug investigation). Lower coordination risk; high value from parallel exploration.

### 7. Monitor and steer
Don't let a team run unattended for too long. Check progress, redirect stuck teammates, synthesize findings as they arrive.

---

## Use Case Examples

### Parallel Code Review
```
Create an agent team to review PR #142. Spawn three reviewers:
- One focused on security implications
- One checking performance impact
- One validating test coverage
Have them each review and report findings.
```
Each reviewer applies a different lens to the same PR. Lead synthesizes across all three.

### Competing Hypotheses Debugging
```
Users report the app exits after one message instead of staying connected.
Spawn 5 agent teammates to investigate different hypotheses. Have them talk to
each other to try to disprove each other's theories, like a scientific
debate. Update the findings doc with whatever consensus emerges.
```
Key mechanism: adversarial structure. Sequential investigation anchors on the first plausible theory. Parallel investigators actively trying to disprove each other surface the actual root cause.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Teammates not appearing | Press Shift+Down in in-process mode; verify `which tmux` if using split panes |
| Too many permission prompts | Pre-approve common operations in permission settings before spawning |
| Teammate stops on error | Check output via Shift+Down; give direct instructions or spawn replacement |
| Lead shuts down early | Tell it to keep going or wait for teammates to finish |
| Orphaned tmux session | `tmux ls` → `tmux kill-session -t <session-name>` |
| Task status lagging | Check if work is done; update status manually or tell lead to nudge teammate |

---

## Known Limitations

| Limitation | Detail |
|---|---|
| No session resumption (in-process) | `/resume` and `/rewind` don't restore in-process teammates |
| Task status lag | Teammates sometimes fail to mark tasks complete; blocks dependencies |
| Slow shutdown | Teammates finish current request before shutting down |
| One team at a time | Clean up before creating a new one |
| No nested teams | Teammates cannot spawn their own teams; only the lead can |
| Lead is fixed | Can't promote a teammate to lead or transfer leadership |
| Permissions set at spawn | Can't set per-teammate modes at spawn time |
| Split panes limited | Not supported in VS Code integrated terminal, Windows Terminal, or Ghostty |

---

## Quick Reference Card

```
ENABLE:   settings.json → env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS = "1"
VERSION:  claude --version (requires v2.1.32+)

START:    "Create an agent team to [task]. Spawn [N] teammates: one for X, one for Y..."
CYCLE:    Shift+Down (in-process mode)
TOGGLE:   Ctrl+T (task list)
CLEANUP:  "Clean up the team" (via lead, after shutting down teammates)

IDEAL TEAM SIZE:     3–5 teammates, 5–6 tasks each
IDEAL TASK SIZE:     Self-contained unit with clear deliverable
AVOID:               Same-file edits, sequential tasks, many dependencies
```
