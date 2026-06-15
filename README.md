# Discord Casino Bot

A Python Discord bot with virtual chip games (coinflip, blackjack, Texas Hold'em), prefix + slash commands, server logging, and moderation tools.

## Setup

1. Create a bot at https://discord.com/developers/applications
2. Enable **Message Content Intent** and **Server Members Intent** under Bot settings
3. Copy `.env.example` to `.env` and set your `DISCORD_TOKEN`
4. Install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

5. Invite the bot to your server with Administrator (or at least Manage Messages, Kick/Ban Members, Moderate Members, Manage Channels)
6. Run the bot:

```bash
python bot.py
```

## After the bot is online

1. Run **`/setup`** or **`!setup`** for a step-by-step checklist
2. Run **`/settings`** → **Set log channel** and pick a private staff channel
3. Optionally change the prefix in **`/settings`** → **Set prefix** (default: `!`)
4. Test prefix commands, e.g. `!coinflip 50 heads` or `!poker 100`
5. Test slash commands, e.g. `/coinflip`, `/poker`, `/balance`

## Prefix commands

The bot supports **both** slash commands and text prefix commands.

- Default prefix: `!` (change per server in `/settings`)
- You can also mention the bot: `@CasinoBot help`
- Examples:
  - `!balance`
  - `!coinflip 100 heads`
  - `!blackjack 50`
  - `!poker 25`
  - `!settings`
  - `!purge 10`

Set `DEFAULT_PREFIX` in `.env` to change the fallback prefix for new servers.

## Commands

| Command | Description |
|---------|-------------|
| `/balance` | Check your chips |
| `/daily` | Claim daily reward |
| `/leaderboard` | Top balances |
| `/coinflip bet choice` | 50/50 bet on heads or tails |
| `/blackjack bet` | Play blackjack with Hit / Stand / Double |
| `/poker bet` | Texas Hold'em showdown vs bot |
| `/settings` | Server settings menu (prefix, logs, casino) |
| `/setup` | Quick setup guide |
| `/help` | Command list |
| `/kick`, `/ban`, `/timeout`, `/purge` | Moderation tools |

## Server logging

Configure in `/settings`:

- **Log channel** — where events are posted
- **Member logs** — joins, leaves, role changes
- **Message logs** — edits and deletes
- **Moderation logs** — bans, kicks, purges, slowmode
- **Game logs** — casino game results

## Cloud hosting

Deploy as a long-running process (Railway, Fly.io, or a VPS). Set `DISCORD_TOKEN` as an environment variable and use `python bot.py` as the start command.
