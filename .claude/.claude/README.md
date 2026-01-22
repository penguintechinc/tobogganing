# Claude Context Files

This directory contains focused standards files for Claude Code to reference when working on specific parts of the codebase.

## 🚫 DO NOT MODIFY EXISTING FILES

**These are centralized template standards that will be overwritten when updated.**

Files you must **NEVER modify**:
- `go.md`, `python.md`, `react.md` (language standards)
- `flask-backend.md`, `go-backend.md`, `webui.md` (service standards)
- `database.md`, `security.md` (domain standards)
- `README.md` (this file)

**Instead, CREATE NEW FILES for app-specific context:**
- `.claude/app.md` - App-specific rules and context
- `.claude/[feature].md` - Feature-specific context (e.g., `billing.md`, `notifications.md`)
- `docs/APP_STANDARDS.md` - Human-readable app-specific documentation

---

## ⚠️ CRITICAL RULES

Every file in this directory starts with a "CRITICAL RULES" section. Claude should read and follow these rules strictly.

## File Index

### Language Standards
| File | When to Read |
|------|--------------|
| `go.md` | Working on Go code (*.go files) |
| `python.md` | Working on Python code (*.py files) |
| `react.md` | Working on React/frontend code (*.jsx, *.tsx files) |

### Service Standards
| File | When to Read |
|------|--------------|
| `flask-backend.md` | Working on Flask backend service |
| `go-backend.md` | Working on Go backend service |
| `webui.md` | Working on WebUI/React service |

### Domain Standards
| File | When to Read |
|------|--------------|
| `database.md` | Any database operations (PyDAL, SQLAlchemy, GORM) |
| `security.md` | Authentication, authorization, security scanning |
| `testing.md` | Running tests, beta infrastructure, smoke tests |

## Usage

Claude should:
1. Read the main `CLAUDE.md` for project overview and critical rules
2. Read relevant `.claude/*.md` files based on the task at hand
3. Follow the CRITICAL RULES sections strictly - these are non-negotiable

## File Size Limit

All files in this directory should be under 5000 characters to ensure Claude can process them effectively.
