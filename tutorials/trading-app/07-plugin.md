# Chapter 7: Plugin

## What Happens

Customize the plugin skeleton for the trading app.

## Commands to Create

| Command | Description |
|---------|-------------|
| /trade-help | Show available trading commands |
| /trade-listings | Browse marketplace listings |
| /trade-quote | Get a DEX swap quote |
| /trade-balance | Check wallet balance |
| /trade-history | View transaction history |

## Steps

1. Create command files in `plugin/commands/` for each command above
2. Update `plugin/skills/app/SKILL.md` with trading tool descriptions
3. Update `plugin/hooks/context.json` with the command list
4. Update `plugin/.claude-plugin/plugin.json` with trading app metadata
5. Test by installing: `claude plugin install ./plugin`

## Expected Output

- Working Claude Code plugin with 5+ commands
- Plugin installable and functional

## Next

Proceed to [Chapter 8: Deployment](08-deployment.md)
