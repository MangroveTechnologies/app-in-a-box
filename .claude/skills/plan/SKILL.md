---
name: plan
description: >-
  Use after /architecture is approved. Generates a phased implementation plan
  with tasks, dependencies, agent assignments, and a scaffold cleanup step.
  Writes docs/implementation-plan.md. Gate: user approves, then product-owner
  agent activates to drive execution.
---

# Implementation Planning

Generate a phased implementation plan from the approved architecture. This is the last skill in the design chain — after this, the product-owner agent takes over.

**Announce at start:** "I'm creating the implementation plan from your approved architecture. This breaks the work into phases and tasks that the agent workforce can execute."

## Inputs

Read these files (all required):
- `docs/architecture.md` — approved architecture with diagrams and module decisions
- `docs/specification.md` — approved spec for API contracts and data models
- `docs/requirements.md` — approved requirements for acceptance criteria
- `CLAUDE.md` — project context and experience level

If any are missing, tell the user which phase they need to complete first.

## Process

### Step 1: Identify Phases

Break the implementation into logical phases. Each phase should produce a working, testable increment. Typical phases:

1. **Foundation** — Project restructure, scaffold cleanup, core configuration
2. **Data Layer** — Database models, migrations, connection pooling (if applicable)
3. **Service Layer** — Business logic implementation
4. **API Layer** — REST routes and MCP tools
5. **Auth & Payments** — Authentication middleware, x402 integration (if applicable)
6. **Plugin** — Claude Code plugin commands, skills, hooks
7. **Testing** — Integration tests, end-to-end verification
8. **Deployment** — Docker, CI/CD, Terraform updates

Phases may be added, removed, or reordered based on the architecture.

### Step 2: Define Tasks per Phase

For each phase, create tasks following the writing-plans format:

- Each task has clear **Files** (create/modify/test)
- Each task has bite-sized **Steps** (2-5 minutes each)
- Steps follow TDD: write test → run to fail → implement → run to pass → commit
- Include exact file paths, code snippets, and test commands
- No placeholders — every step has complete content

### Step 3: Assign Agent Roles

For each task, specify which agent type should handle it:

| Task | Agent | Reason |
|------|-------|--------|
| Scaffold cleanup | backend-developer | File moves, config updates |
| Data models | backend-developer | Database schema, Pydantic models |
| Service logic | backend-developer | Business logic implementation |
| REST routes | backend-developer | Endpoint implementation |
| MCP tools | backend-developer | Tool registration and implementation |
| Auth middleware | backend-developer | Auth flow implementation |
| Plugin commands | backend-developer | Markdown command files |
| Unit tests | test-engineer | Test design and implementation |
| Integration tests | test-engineer | E2E test design |
| Docker/CI updates | devops-engineer | Dockerfile, workflow updates |
| Code review | code-review | Post-task review (automatic via subagent-driven-development) |
| Architecture diagrams | diagram-agent | Diagram validation |

### Step 4: Include Scaffold Cleanup

The first phase MUST include a scaffold cleanup task based on the module retention decisions from the architecture phase. This task:

- Removes modules marked for removal in `docs/architecture.md`
- Updates configuration files to remove references to removed modules
- Updates docker-compose.yml to remove unused services
- Updates tests to remove tests for removed modules
- Updates CLAUDE.md to reflect the actual project structure

### Step 5: Present to User

Present the plan as an overview:

> "Here's the implementation plan:"
> - **Phase 1: {name}** — {N tasks, estimated time}
> - **Phase 2: {name}** — {N tasks, estimated time}
> - ...
> - **Total: {N tasks} across {N phases}"
>
> "Each task is designed to be handled by a specific agent type. The product-owner agent will coordinate execution."

### Step 6: Write Implementation Plan Document

When the user approves, write `docs/implementation-plan.md` following the writing-plans format:

```markdown
# {Project Name} Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** {One sentence from requirements}

**Architecture:** {2-3 sentences from architecture doc}

**Tech Stack:** {Key technologies}

**Spec:** docs/specification.md
**Architecture:** docs/architecture.md
**Requirements:** docs/requirements.md

---

## Phase 1: {Phase Name}

### Task 1: {Task Name}

**Agent:** {agent type}
**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py`
- Test: `tests/exact/path/test.py`

- [ ] **Step 1: ...**
{Exact content — code, commands, expected output}

- [ ] **Step 2: ...**
{Exact content}

...

## Phase N: {Phase Name}

### Task N: {Task Name}
...
```

## Gate

After writing the document:

> "Implementation plan written to `docs/implementation-plan.md`."
>
> "{N tasks} across {N phases}. The product-owner agent will drive execution using the agent workforce."
>
> "Say 'approved' to activate the product owner and begin implementation, or tell me what to change."

Wait for explicit approval.

## Hand Off

When approved:

> "The product-owner agent is now active. It will read the implementation plan and begin coordinating the agent workforce to build your app."
>
> "You can check progress at any time by asking the product owner for a status update."

The product-owner agent (`.claude/agents/product-owner.md`) takes over from here using `subagent-driven-development` or `executing-plans` superpowers skills.

## Re-entry

If `docs/implementation-plan.md` already exists:

> "I see an existing implementation plan. Do you want to revise it, regenerate from the current architecture, or continue where it left off?"

## Notes

- The plan must be traceable: every task maps to a spec endpoint or architecture component.
- Scaffold cleanup is always Phase 1, Task 1. Get the house in order before building.
- Time estimates are rough guides, not commitments. Agents work at different speeds.
- The plan should be executable by an agent with no additional context beyond the plan document and the three upstream docs (requirements, specification, architecture).
- Follow the superpowers writing-plans format exactly — the subagent-driven-development skill expects this structure.
