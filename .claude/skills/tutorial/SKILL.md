---
name: tutorial
description: >-
  Interactive guided walkthrough for building a trading app using the Mangrove
  developer API. Follows the 8 tutorial chapters in tutorials/trading-app/
  and walks the user through the full app-in-a-box lifecycle.
---

# Tutorial: Build a Trading App

Interactive guided walkthrough that teaches the app-in-a-box lifecycle by building a trading app against the Mangrove developer API.

**Announce at start:** "Welcome to the app-in-a-box tutorial! We're going to build a trading app that connects to the Mangrove developer API. By the end, you'll have a working app with a Claude Code plugin."

## Prerequisites

Before starting, verify:
- Docker is installed: `docker --version`
- Claude Code is installed: `claude --version`
- The app-in-a-box repo is cloned and you're in it

If anything is missing, help the user install it.

## Structure

This tutorial follows 8 chapters. Each chapter has:
- Reference docs in `tutorials/trading-app/`
- An interactive guided experience right here

Adapt explanations to the user's experience level (check CLAUDE.md for `experience_level`).

## Chapter 0: Overview

> "We're building a trading app that lets agents and users interact with the Mangrove marketplace. The app will have:"
> - REST API endpoints for trading operations
> - MCP tools for agent access
> - A Claude Code plugin for easy interaction
>
> "This tutorial walks through the entire app-in-a-box lifecycle: onboarding → requirements → specification → architecture → plan → build → plugin → deploy."

Reference: `tutorials/trading-app/00-overview.md`

## Chapter 1: Onboarding

Run the user through `/onboard` with trading-app-specific guidance:

> "Let's start by setting up the project. I'll walk you through the onboarding process."

Invoke `/onboard`. The user should answer with trading-app context:
- Building: A trading app using the Mangrove developer API
- Why: Learning the app-in-a-box lifecycle
- Experience: Their actual level

Reference: `tutorials/trading-app/01-onboarding.md`

## Chapter 2: Requirements

Run the user through `/requirements` with trading-app-specific guidance:

> "Now let's define what the trading app needs to do."

Invoke `/requirements`. Guide the user toward these core features:
- Query marketplace listings
- Get DEX swap quotes
- Check wallet balances
- View transaction history
- Authentication via API key

Reference: `tutorials/trading-app/02-requirements.md`

## Chapter 3: Specification

Run the user through `/specification`:

> "Let's turn those requirements into a technical spec."

Invoke `/specification`. The spec should define endpoints matching the Mangrove developer API patterns.

Reference: `tutorials/trading-app/03-specification.md`

## Chapter 4: Architecture

Run the user through `/architecture`:

> "Now let's design the architecture."

Invoke `/architecture`. The architecture should show the trading app calling the Mangrove API as an external integration.

Reference: `tutorials/trading-app/04-architecture.md`

## Chapter 5: Implementation Plan

Run the user through `/plan`:

> "Let's create the implementation plan."

Invoke `/plan`.

Reference: `tutorials/trading-app/05-implementation.md`

## Chapter 6: Building

> "Now the product owner takes over to build the app. This is where the agent workforce does the heavy lifting."

The product owner activates and executes the implementation plan. Walk the user through what's happening at each step.

Reference: `tutorials/trading-app/06-building.md`

## Chapter 7: Plugin

> "The app is built! Now let's create the Claude Code plugin so users can interact with it."

Guide the user through customizing the plugin skeleton:
- Update commands for trading operations
- Update the skill with trading tool descriptions
- Update hooks with trading context
- Test the plugin by installing it locally

Reference: `tutorials/trading-app/07-plugin.md`

## Chapter 8: Deployment

> "Final step — let's deploy."

Walk through:
- Docker build and local testing
- Terraform setup (if deploying to GCP)
- CI/CD pipeline verification

Reference: `tutorials/trading-app/08-deployment.md`

## Completion

> "Congratulations! You've built a complete trading app using app-in-a-box. You now have:"
> - A working FastAPI server with REST + MCP endpoints
> - A Claude Code plugin for easy interaction
> - Full documentation (requirements, spec, architecture, plan)
> - Docker + CI/CD ready for deployment
>
> "You can now use this same process to build anything. Just start a new project with app-in-a-box and run `/onboard`."

## Notes

- The tutorial chapters in `tutorials/trading-app/` contain the reference material. This skill provides the interactive experience.
- If the user gets stuck, refer them to the relevant tutorial doc.
- The tutorial is also a validation test for the entire skill chain. If it produces a working app, the framework works.
- Don't rush. Let the user absorb each phase before moving to the next.
