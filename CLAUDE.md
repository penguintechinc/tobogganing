# Claude Code Context (.claude/ supplement)

**This file supplements the root `/CLAUDE.md`.** It contains only rules and configuration unique to the `.claude/` directory context. For project overview, structure, commands, standards references, CI/CD, and all other shared context, see the root `CLAUDE.md`.

**Precedence**: `~/.claude/rules/*.md` wins over this file on conflict.

## 🚫 DO NOT MODIFY THIS FILE OR `.claude/` STANDARDS

**These are centralized template files that will be overwritten when standards are updated.** (`docs/STANDARDS.md` and `docs/standards/` are NOT distributed here — `admin` is their sole source of truth.)

- ❌ **NEVER edit** `CLAUDE.md` or `.claude/*.md`
- ✅ **CREATE NEW FILES** for app-specific context:
  - `docs/APP_STANDARDS.md` - App-specific architecture, requirements, context
  - `.claude/{subject}.local.md` - Project-specific overrides (e.g., `architecture.local.md`, `python.local.md`)

**App-Specific Addendums to Standardized Files:**

If your app needs to add exceptions, clarifications, or context to standardized `.claude/` files (e.g., `react.md`, `python.md`, `testing.md`), **DO NOT edit those files**. Instead, create a `.local` variant:

- `react.md` (standardized) → Create `react.local.md` for app-specific React patterns
- `python.md` (standardized) → Create `python.local.md` for app-specific Python decisions
- `testing.md` (standardized) → Create `testing.local.md` for app-specific test requirements
- `security.md` (standardized) → Create `security.local.md` for app-specific security rules

**Local Repository Overrides:**

This repository may contain `.local.md` variant files that provide project-specific overrides or addendums:
- `CLAUDE.local.md` - Project-specific additions or clarifications to this CLAUDE.md
- `.claude/*.local.md` - Project-specific overrides to standardized `.claude/` rules

**Always check for and read `.local.md` files** alongside standard files to ensure you have the complete context for this specific repository.

## Global vs Local Rules and Skills

**Standard rules/skills/agents are symlinked globally at `~/.claude/{rules,skills,agents}/`** via `make sync-standards` (`scripts/sync-standards.sh`; source: `~/code/admin/.claude/{rules,skills,agents}/`) — NOT copied into individual repos.

- **Global** (`~/.claude/rules/*.md`, `~/.claude/skills/*/SKILL.md`): Managed centrally, apply to all projects
- **Local** (`{REPO_ROOT}/.claude/rules/*.local.md`, `{REPO_ROOT}/.claude/skills/*/*.local.md`): Project-specific overrides, stay in the repo

`make sync-standards-local` refreshes only the symlinks (no downstream repo push); preserves `.local.md` files.

---

## MCP Servers

- **mem0**: Canonical persistent memory layer — always preferred over file-based memory (`.PLAN`/`.TODO` are crash-recovery only, not a substitute). `search_memories` at the start of every session before asking the user to re-explain anything; `add_memory` for architecture, conventions, debugging insights, decisions, preferences; `update_memory` when prior context changes. When in doubt, save it. **If the mem0 server is unreachable, say so explicitly in your report** (e.g. "mem0 unreachable — recall skipped") — graceful degradation must stay visible, never silent.
- **gemini**: Research (Google Search grounding) and media generation, exposed via the `gemini-expert` agent and `gemini-research`/`gemini-create`/`gemini-api-dev` skills. Prefer over WebSearch for research, and for image/video/audio generation. All seven tools run on the `google-genai` SDK and require `GEMINI_API_KEY` — see Setup Script below.

---

## Setup Script

This repo includes `setup.sh` which configures the local Claude Code environment:

```bash
.claude/setup.sh              # Full setup (statusline + mem0 + gemini + settings)
.claude/setup.sh statusline   # Statusline only
.claude/setup.sh mem0         # mem0 + Qdrant only
.claude/setup.sh gemini       # Gemini MCP only
.claude/setup.sh settings     # Settings update only
```

At session start, verify the environment is configured. If `~/.claude/statusline-command.sh`, `~/.claude/mcp/mem0/mcp-server.py`, or `~/.claude/mcp/gemini/mcp-server.py` does not exist, run `setup.sh` from this repo.

### Status Line

The setup script symlinks `statusline-command.sh` to `~/.claude/` and configures `settings.json`. The statusline displays model, effort, repo, branch, context usage, cost, and duration.

### mem0 (Local Persistent Memory)

The setup script deploys a local Qdrant container and configures a mem0 MCP server using Ollama for embeddings (`nomic-embed-text`) and LLM (`gemma3:1b`). All memory operations are fully local — no external API calls.

**Manage Qdrant:**
```bash
docker compose -f ~/.claude/mcp/mem0/docker-compose.yml up -d    # start
docker compose -f ~/.claude/mcp/mem0/docker-compose.yml down      # stop
```

**Qdrant dashboard:** http://localhost:6333/dashboard

### Gemini (Research & Media Generation)

The setup script deploys the Gemini MCP server to `~/.claude/mcp/gemini/` with its own venv and registers the server with Claude Code. It powers the `gemini-expert` agent (research, second opinions, image/video/music generation) and the `gemini-research`/`gemini-create`/`gemini-api-dev` skills.

**One auth path for all seven tools**, two ways to supply it (get a key at https://aistudio.google.com/apikey — the free tier works, including Search grounding, no billing required):
- Export `GEMINI_API_KEY` in your shell profile, or
- Save the key to `~/.gemini-token`, owner-read-only (`chmod 400 ~/.gemini-token`) — the server reads this file at startup only when no `GEMINI_API_KEY`/`GOOGLE_API_KEY` is already in the environment.

Never pass it as a literal CLI argument or paste it into chat — the setup script does not bake it into the MCP registration. Text/reasoning tools (research, prompt, second_opinion, analyze) use Google Search grounding on the standard API-key tier via `google-genai`'s `generate_content`. There is no separate CLI login step — the old free-OAuth `gemini` CLI path (`gemini auth`) was retired by Google on 2026-06-18 and is no longer used here.
