---
name: onboard
description: >-
  Use on first session in a fresh app-in-a-box repo. Guides the user through
  project setup via conversation — learns what they're building, why, their
  experience level, and preferences. Populates branding.json and CLAUDE.md.
---

# Onboarding

Welcome the user to app-in-a-box. This skill runs once — on the first Claude session in a fresh repo. After onboarding completes, hand off to the /requirements skill.

**Announce at start:** "Welcome to app-in-a-box! I'm going to ask you a few questions to set up your project. This takes about 5 minutes."

## Detection

Trigger automatically when ALL of these are true:
- `docs/requirements.md` does not exist
- `branding.json` still contains `"project_name": "app-in-a-box"` (hasn't been customized)
- User hasn't explicitly skipped onboarding

If the user has already run `init.sh`, detect that the project name has changed and skip to Phase 2.

## Phase 1: Get to Know the User

Ask these questions **one at a time**. Wait for each answer before asking the next. Use plain language — the user may have no software engineering background.

### Question 1: What are you building?

> "What are you building? Just describe it in your own words — no technical jargon needed."

Listen for: the core idea, who it's for, what problem it solves. Store this as `project_description`.

### Question 2: Why are you building it?

> "What's driving this? Is this for work, a side project, learning, a startup idea?"

Listen for: motivation, urgency, constraints. Store as `project_motivation`.

### Question 3: Experience level

> "How would you describe your coding experience?"
> - **Beginner** — I'm just getting started or mostly self-taught
> - **Intermediate** — I've built things before but not production systems
> - **Advanced** — I ship production code regularly

Store as `experience_level`. This calibrates how much the agent explains in subsequent phases.

### Question 4: Preferences

> "Anything you want me to know about how you like to work? Coding style, naming preferences, tools you love or hate — anything goes. Or just say 'no preferences' and we'll use sensible defaults."

Store as `user_preferences`.

### Question 5: Project identity

> "What should we call your project? I'll also need:"
> - Project name (used in code, lowercase-with-dashes)
> - Display name (used in docs and UI)
> - Your name or org name
> - A short tagline (optional)

If the user provides branding assets (logos, icons), organize them into the `assets/` directory using these conventions:
- Main logo → `assets/logo.svg` (or `.png`)
- Dark/inverted logo → `assets/logo-dark.svg` (or `.png`)
- Icon/mark → `assets/icon.png`
- Banner → `assets/banner.png`

Accept whatever the user gives and do the work to organize it.

## Phase 1 Outputs

After collecting answers:

1. **Update `branding.json`** with project name, display name, org name, tagline, and any URLs provided.

2. **Update `CLAUDE.md`** — add a "Project Context" section at the top:

```markdown
## Project Context

**What:** {project_description}
**Why:** {project_motivation}
**Experience level:** {experience_level}
**Preferences:** {user_preferences}
```

3. **Present summary to user for confirmation:**

> "Here's what I've got:"
> - Project: {display_name}
> - Description: {project_description}
> - Experience: {experience_level}
> "Does this look right? Any changes?"

Wait for confirmation.

## Phase 2: Hand Off

After user confirms:

> "Great! Your project is set up. Next step is gathering requirements — I'll help you think through what your app needs to do, and we'll create user flow diagrams to make sure we're aligned."
>
> "Ready to start? Just say 'yes' or run `/requirements` when you're ready."

When user is ready, invoke the `/requirements` skill.

## Skip Path

If the user says "skip" or "I already know what I want", respect it:

> "No problem. You can always come back to this with `/onboard`. Your project is ready — run `/requirements` when you want to start the design process, or just start coding."

## Notes

- One question at a time. Never batch questions.
- If the user gives short answers, that's fine. Don't push.
- If the user gives long, detailed answers, extract the key points and confirm.
- Plain language always. If you need to use a technical term, explain it.
- The onboarding conversation sets the tone for the entire experience. Be warm, not robotic.
