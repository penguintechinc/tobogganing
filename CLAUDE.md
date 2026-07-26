# Claude Code Context (.claude/ supplement)

**This file supplements the root `/CLAUDE.md`.** It contains only rules and configuration unique to the `.claude/` directory context. For project overview, structure, commands, standards references, CI/CD, and all other shared context, see the root `CLAUDE.md`.

## 🚫 DO NOT MODIFY THIS FILE OR `.claude/` STANDARDS

**These are centralized template files that will be overwritten when standards are updated.**

- ❌ **NEVER edit** `CLAUDE.md`, `.claude/*.md`, `docs/STANDARDS.md`, or `docs/standards/*.md`
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

**Standard rules and skills are installed globally at `~/.claude/{rules,skills}/`** by the `update_standards.sh` script in the `admin` repo. They are NOT symlinked into individual repos.

- **Global** (`~/.claude/rules/*.md`, `~/.claude/skills/*/SKILL.md`): Managed centrally, apply to all projects
- **Local** (`{REPO_ROOT}/.claude/rules/*.local.md`, `{REPO_ROOT}/.claude/skills/*/*.local.md`): Project-specific overrides, stay in the repo

The `update_standards.sh` script copies rules/skills from `~/code/.claude/` to `~/.claude/` and cleans up old per-repo symlinks (preserving `.local.md` files).

---

## MCP Servers

- **mem0**: Persistent memory across sessions. At the start of each session, `search_memories` for relevant context before asking the user to re-explain anything. Use `add_memory` whenever you discover project architecture, coding conventions, debugging insights, key decisions, or user preferences. Use `update_memory` when prior context changes. Save information like: "This project uses PostgreSQL with Prisma", "Tests run with pytest -v", "Auth uses JWT validated in middleware". When in doubt, save it, future sessions benefit from over-remembering.

---

## Setup Script

This repo includes `setup.sh` which configures the local Claude Code environment:

```bash
.claude/setup.sh              # Full setup (statusline + mem0 + settings)
.claude/setup.sh statusline   # Statusline only
.claude/setup.sh mem0         # mem0 + Qdrant only
.claude/setup.sh settings     # Settings update only
```

At session start, verify the environment is configured. If `~/.claude/statusline-command.sh` or `~/.claude/mcp/mem0/mcp-server.py` does not exist, run `setup.sh` from this repo.

### Status Line

The setup script symlinks `statusline-command.sh` to `~/.claude/` and configures `settings.json`. The statusline displays model, effort, repo, branch, context usage, cost, and duration.

### mem0 (Local Persistent Memory)

The setup script deploys a local Qdrant container for vector storage and configures a mem0 MCP server using Ollama for embeddings (`nomic-embed-text`) and LLM (`llama3.2:3b`). All memory operations are fully local — no external API calls.

**Manage Qdrant:**
```bash
docker compose -f ~/.claude/mcp/mem0/docker-compose.yml up -d    # start
docker compose -f ~/.claude/mcp/mem0/docker-compose.yml down      # stop
```

**Qdrant dashboard:** http://localhost:6333/dashboard
