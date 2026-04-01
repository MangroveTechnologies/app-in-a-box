# Chapter 6: Building

## What Happens

The product owner agent drives implementation using the agent workforce.

## What to Expect

- The product owner dispatches tasks to backend-developer, test-engineer, etc.
- Each task follows TDD: write test → run to fail → implement → run to pass → commit
- Two-stage review after each task: spec compliance, then code quality
- You can check progress at any time

## Your Role

- Review and approve when asked
- Answer questions if the agents need clarification
- Test the running app periodically: `docker compose up -d --build && curl http://localhost:8080/health`

## Expected Output

- Working FastAPI server with all endpoints
- Passing tests
- Ready for plugin and deployment

## Next

Proceed to [Chapter 7: Plugin](07-plugin.md)
