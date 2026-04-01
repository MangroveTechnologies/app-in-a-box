---
name: specification
description: >-
  Use after /requirements is approved. Generates a technical specification from
  approved requirements — API contracts, data models, error handling, auth flows,
  integrations. Writes docs/specification.md. Gate: user approves before
  moving to /architecture.
---

# Technical Specification

Transform approved requirements into a technical specification that defines HOW the system will work.

**Announce at start:** "I'm generating the technical specification from your approved requirements. This defines the API contracts, data models, and system behavior."

## Inputs

Read these files (all required):
- `docs/requirements.md` — approved requirements with user stories and flow diagrams
- `CLAUDE.md` — project context, experience level, preferences
- `branding.json` — project identity

If `docs/requirements.md` doesn't exist or isn't approved, tell the user to run `/requirements` first.

## Process

### Step 1: Analyze Requirements

Read all user stories and flow diagrams. Identify:

- **Entities:** What data objects exist? (users, items, orders, etc.)
- **Actions:** What operations can be performed on each entity?
- **Relationships:** How do entities relate to each other?
- **External integrations:** What third-party APIs or services are needed?
- **Auth model:** Who can do what?

### Step 2: Design API Contracts

For each action identified in Step 1, define the API endpoint:

```markdown
### POST /api/v1/{resource}

**Description:** {What it does}
**Auth:** {free | api-key | x402}

**Request:**
\```json
{
  "field": "type — description"
}
\```

**Response (201):**
\```json
{
  "id": "string — unique identifier",
  "field": "type — description",
  "created_at": "string — ISO 8601 timestamp"
}
\```

**Errors:**
- 400: {When and why}
- 401: {When and why}
- 404: {When and why}
```

Follow these conventions (matching x402-app-template patterns):
- Free endpoints: `/api/v1/{resource}`
- Auth-gated endpoints: `/api/v1/{resource}` with X-API-Key header
- x402 payment-gated: `/api/x402/{resource}`
- MCP tools mirror REST endpoints — same service layer, different interface

### Step 3: Define Data Models

For each entity, define the Pydantic model:

```python
class EntityName(BaseModel):
    id: str
    field: type  # description
    created_at: datetime
```

Include:
- Field types and constraints (min/max length, regex patterns, enums)
- Required vs optional fields
- Relationships (foreign keys, references)
- Indexes needed for query patterns

### Step 4: Define Error Handling

Standard error response format:

```json
{
  "error": true,
  "code": "ERROR_CODE",
  "message": "Human-readable description",
  "suggestion": "What to do about it"
}
```

List all error codes the system will use, grouped by category.

### Step 5: Define Auth Flows

Based on requirements, specify:
- Which endpoints are free, auth-gated, or payment-gated
- API key validation flow
- x402 payment flow (if applicable)
- Any role-based access control

### Step 6: Define External Integrations

For each external system:
- API endpoint and auth method
- Request/response format
- Rate limits and retry strategy
- Failure handling (what happens when the external system is down?)

### Step 7: Present to User

Present the full specification section by section. Adapt detail level to experience:

- **Beginner:** Focus on what each endpoint does in plain language. Show example requests/responses. Skip internal details.
- **Intermediate:** Show API contracts with types. Explain data model relationships.
- **Advanced:** Full detail — models, error codes, auth flows, integration specs.

After each section:

> "Does this look right for {section name}? Any changes?"

### Step 8: Write Specification Document

When the user approves all sections, write `docs/specification.md`:

```markdown
# Technical Specification: {Project Name}

**Generated:** {date}
**Status:** Approved
**Based on:** docs/requirements.md

## Overview

{Brief technical summary — what the system does and how}

## API Contracts

### {Resource 1}

{Endpoints with request/response contracts}

### {Resource 2}

{Endpoints with request/response contracts}

## MCP Tools

{Tool definitions mirroring REST endpoints}

## Data Models

{Pydantic model definitions}

## Error Handling

{Error codes and response format}

## Authentication & Authorization

{Auth flows and access tiers}

## External Integrations

{Integration specs}

## Configuration

{Required and optional configuration keys}
```

## Gate

After writing the document:

> "Specification written to `docs/specification.md`. Please review. When you approve, we'll design the system architecture."
>
> "Say 'approved' to proceed to /architecture, or tell me what to change."

Wait for explicit approval.

## Hand Off

When approved, invoke the `/architecture` skill.

## Re-entry

If `docs/specification.md` already exists:

> "I see an existing specification. Do you want to revise it or regenerate from the current requirements?"

## Notes

- The spec must be traceable to requirements. Every endpoint should map to at least one user story.
- Use the x402-app-template patterns as the reference implementation. The server/ directory already demonstrates the service layer pattern, auth middleware, MCP tool registration, and x402 payment flow.
- Don't over-specify. If the requirements are simple, the spec should be simple.
- MCP tools MUST mirror REST endpoints through a shared service layer — never duplicate business logic.
