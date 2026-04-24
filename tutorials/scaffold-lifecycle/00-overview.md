# Tutorial: Build a Trading App with App-in-a-Box

## Overview

This tutorial walks you through building a trading app that connects to the Mangrove developer API using the app-in-a-box template.

## What You'll Build

A FastAPI application that:
- Queries the Mangrove marketplace for listings
- Gets DEX swap quotes across decentralized exchanges
- Checks XRPL wallet balances
- Tracks transaction history
- Exposes all features via REST API and MCP tools
- Includes a Claude Code plugin for easy interaction

## Prerequisites

- Python 3.11+
- Docker
- Claude Code CLI
- A Mangrove developer API key (get one at mangrovedeveloper.ai)

## Chapters

| Chapter | Topic | Time |
|---------|-------|------|
| 01 | Onboarding | 5 min |
| 02 | Requirements | 15 min |
| 03 | Specification | 15 min |
| 04 | Architecture | 10 min |
| 05 | Implementation Plan | 10 min |
| 06 | Building | 30-60 min |
| 07 | Plugin | 15 min |
| 08 | Deployment | 15 min |

## Getting Started

Clone app-in-a-box and start Claude Code:

```bash
git clone https://github.com/MangroveTechnologies/app-in-a-box.git my-trading-app
cd my-trading-app
claude
```

The agent will detect a fresh project and start the onboarding process. Or run `/tutorial` for the guided experience.
