# 📝 Documentation Guide - Write Docs People Actually Read

Part of [Development Standards](../STANDARDS.md)

## Why Documentation Matters (Even Though It's Boring)

Good docs = happy developers = fewer "why doesn't this work?!" Slack messages = everyone's sanity stays intact. Think of docs as your future self's love letter—be nice to them.

## 📁 Where Things Go

```
docs/
├── README.md            ← Everyone reads this first
├── DEVELOPMENT.md       ← How to set up locally
├── TESTING.md          ← Mock data & smoke tests
├── DEPLOYMENT.md       ← Production setup
├── RELEASE_NOTES.md    ← What's new (dated entries)
├── APP_STANDARDS.md    ← Your app-specific rules
├── standards/          ← Deep dives on patterns
│   ├── ARCHITECTURE.md
│   ├── DATABASE.md
│   └── ...
└── screenshots/        ← Real feature screenshots
```

## README.md - Your App's First Impression

**Your README is not optional bling.** It's the first thing people (including future-you) see.

**REQUIRED Elements:**
- Build status badges (GitHub Actions, Codecov, License)
- Catchy ASCII art
- Link to www.penguintech.io
- Quick Start (under 2 minutes to "hello world")
- Default dev credentials clearly marked as dev-only
- Key features (3-5 bullet points)
- Links to detailed docs (DEVELOPMENT.md, TESTING.md, etc.)

**Example Quick Start:**
```markdown
## 🚀 Quick Start

### Prerequisites
- Docker | kubectl | Helm | Git | Local K8s cluster (MicroK8s, Docker Desktop K8s, or Podman)

### Get Running (60 seconds)
```bash
make dev
# Opens http://localhost:3000
```

**Default Dev Credentials:**
- Email: `admin@localhost.local` | Password: `admin123`
⚠️ Development only—change immediately in production!

### Next Steps
- Read [DEVELOPMENT.md](docs/DEVELOPMENT.md) for local setup
- Check [TESTING.md](docs/TESTING.md) for testing patterns
```

## ✍️ Writing Docs People Actually Read

**Keep It Short:** Your reader has 30 seconds. Respect that.
- Headings tell the story
- One idea per paragraph
- Use lists instead of paragraphs
- Short sentences

**Show, Don't Tell:**
- Code examples beat explanations
- Screenshot + caption > thousand words
- Real feature screenshots (with mock data) showcase what works

**Be Conversational:**
- Write like you're explaining to a colleague
- Use "we" and "you"—not the robot voice
- Humor is fine. Sarcasm too.

**Structure for Scanning:**
- Emojis in headings ✅
- Bold key terms
- Bullet points everywhere
- Table of contents for long docs

## 💬 Code Comments - Comments That Help

**Good comments answer "WHY"—not "WHAT"**
```python
# ❌ Bad: Explains what the code does
age = (today - birth_date).days // 365

# ✅ Good: Explains why this matters
# Using integer division to avoid fractional ages in age-gated features
age = (today - birth_date).days // 365
```

**Document the gotchas:**
```python
# NOTE: PyDAL doesn't support HAVING without GROUP BY in SQLite
# Use Python filtering for complex aggregations
```

## 📋 Release Notes Template

Create `docs/RELEASE_NOTES.md` and add new releases to the top:

```markdown
# Release Notes

## [v1.2.0] - 2025-01-22

### ✨ New Features
- Feature description

### 🐛 Bug Fixes
- Bug fix description

### 📚 Documentation
- Doc improvement description

## [v1.1.0] - 2025-01-15
...
```

## 🚨 Mistakes to Avoid

| ❌ Wrong | ✅ Right |
|---------|---------|
| "Call the API" (no endpoint) | "POST /api/v1/users with email, password" |
| Outdated screenshots | Fresh screenshots with mock data |
| Assumes prior knowledge | Links to background material |
| Steps with no context | Explains why each step matters |
| One giant wall of text | Short sections with headings |
| Typos and bad grammar | Proofread (spell-check helps!) |

## 📚 CLAUDE.md Management

- **Max 35,000 characters**
- **Stays high-level:** Point to detailed docs, don't repeat them
- **Focus:** Context, workflow rules, architecture decisions
- **Everything else:** Lives in docs/ with proper structure

---

**Golden Rule:** If you wouldn't want to read it, your team won't either. Make docs so clear they're almost impossible to misunderstand.
