# Orchestration & Task Agent Rules

## ⚠️ CRITICAL — READ BEFORE DOING ANY WORK

**The main model (Opus or Sonnet) is the orchestrator. It does NOT do the work.**

This is the single most important rule for token efficiency. The main model — whether Opus or Sonnet — exists to plan, delegate, and validate. All actual implementation is performed by task agents.

## The Orchestration Model

The main model's job:
1. **Plan** — Understand the request, break it into tasks, decide approach
2. **Delegate** — Spawn task agents (Haiku by default) to do all implementation work
3. **Validate** — Review task agent output for correctness
4. **Synthesize** — Combine results and communicate back to the user

The main model does NOT:
- Write code directly
- Edit files directly
- Perform searches or grep operations directly (use Explore agents)
- Read large files to extract information (delegate to a task agent)
- Run builds or tests directly (delegate to a Bash task agent)
- Run linting, security scans, or any validation commands directly

**Builds, tests, and validation are task agent work.** The main model never runs `make build`, `npm test`, `flutter test`, `docker compose up`, `pytest`, or similar commands itself. Delegate these to a task agent and have it report back a summary: pass/fail, error count, and any failure details. The main model then decides what to do next based on that summary.

**The only exception**: Trivial single-line operations (reading a small config, quick git status) where spawning an agent would be slower than doing it directly.

## Model Selection for Task Agents

### Haiku — The Default Worker

**Always start with Haiku.** It handles the vast majority of tasks:
- File searches and exploration
- Code edits (add, modify, delete)
- Writing new files
- Running builds (`make build`, `docker compose build`, `flutter build`, etc.)
- Running tests (`pytest`, `npm test`, `flutter test`, `go test`, etc.)
- Running linters and security scans (`eslint`, `flake8`, `bandit`, `gosec`, etc.)
- Reading files and extracting information
- Simple refactoring
- Grep/glob operations
- Documentation updates

**Builds and tests especially** must be run by task agents. The agent runs the command, captures the output, and reports back a summary: pass/fail, error count, and any failure messages. The main model never sees raw build/test output — only the agent's summary.

### Sonnet — Escalation Only

Escalate to Sonnet ONLY when:
- Haiku produced incorrect output and a retry also failed
- The task requires reasoning across many interconnected files
- Complex architectural decisions that need deep analysis
- Intricate refactoring with subtle dependency chains
- Multi-step logic where Haiku demonstrably struggles

**Never start with Sonnet.** Always try Haiku first. If Haiku fails:
1. Retry the Haiku agent once with a clearer/more specific prompt
2. If still failing, escalate to Sonnet with the same prompt + context about what Haiku got wrong

### Opus/Main Model — Never the Worker

The main model never does implementation work regardless of whether it's Opus or Sonnet. Even if you're running Sonnet as the main model, it still orchestrates — it does not write code directly.

## Task Agent Output Rules

**This prevents context overruns that degrade orchestrator performance.**

### What Task Agents MUST Return

- Error messages (if any)
- Brief completion summary (1-3 sentences)
- File paths that were changed
- Line numbers relevant to the change
- Pass/fail status

### What Task Agents MUST NOT Return

- Full file contents
- Verbose explanations of what the code does
- Raw command output (unless it contains errors)
- Unchanged file contents
- Lengthy analysis or commentary

### How to Enforce This

Every task agent prompt MUST include one of these instructions:
- "Return only errors and a brief summary of what was done."
- "Return file paths changed and any errors. No full file contents."
- "Keep your response concise — errors and summary only."

### Example Prompts

**Good prompt:**
```
Edit /path/to/file.py to add input validation to the create_user function.
Validate that email is non-empty and matches a basic email pattern.
Return only errors and a brief summary of what was changed.
```

**Bad prompt:**
```
Edit /path/to/file.py to add input validation to the create_user function.
Show me the full file after changes.
```

## Plans Must Reference This Pattern

Every implementation plan created by the orchestrator MUST include a section like:

```
## Orchestration
- Main model: plans and validates only — does NOT write code, run builds, or run tests
- Task agents: Haiku (default), Sonnet (escalation only)
- Builds/tests: run by task agents, report pass/fail summary back to main model
- Agent output: errors and brief summaries only — no full file contents or raw command output
```

This ensures the pattern is visible and followed throughout execution.

## Concurrency

- Maximum 10 task agents running concurrently
- Parallelize independent work (searching multiple dirs, editing unrelated files)
- Sequence dependent work (read file → edit file → validate edit)
- Queue additional tasks if at the 10-agent limit

## Token Budget Awareness

The reason for all of these rules:
- **Opus/Sonnet tokens are expensive** — don't waste them writing code that Haiku can write
- **Large agent responses bloat context** — the orchestrator's context window fills up, degrading its planning ability
- **Context overruns cause failures** — when the orchestrator can't see its own prior work, it makes mistakes
- **Haiku is fast and cheap** — use it aggressively for all implementation tasks
- **Sonnet is the middle ground** — capable but still cheaper than Opus, use for genuine complexity only
