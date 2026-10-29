# Discord Slash-Command Bot

A Python Discord bot with `/ping` and `/help` slash commands, powered by `discord.py`.

## Run & Operate

- `uv run discord-bot` — run the bot
- `DISCORD_TOKEN` — required Replit Secret; never commit the token
- `OWNER_ID` — required Replit Secret containing the bot owner's numeric Discord user ID
- `pnpm --filter @workspace/api-server run dev` — run the API server (port 5000)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)

## Stack

- Python 3.13, `discord.py`
- pnpm workspaces, Node.js 24, TypeScript 5.9
- API: Express 5
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)

## Where things live

- `src/discord_bot/` — bot startup and slash-command implementation
- `pyproject.toml` / `uv.lock` — Python dependency and runtime configuration
- `README.md` — Discord application setup and bot instructions

## Architecture decisions

- Slash commands are synced globally when the bot starts.
- Message-content intent is not enabled; commands use Discord interactions only.

## Product

The bot provides French slash commands for moderation, server information, polls, announcements, reports, private tickets, verification panels, and event logs. `/ping` and `/help` remain available.

## User preferences

- Keep the Discord bot token in the `DISCORD_TOKEN` environment variable, never in source code.

## Gotchas

- Invite the bot with both the `bot` and `applications.commands` OAuth2 scopes.
- Global slash-command changes may take time to appear in Discord after syncing.
- Configure the log destination with `/logsetup`, the staff role with `/ticketsetup`, and the verification role with `/verifysetup`.
- `/owner` and every panel interaction enforce an exact server-side `interaction.user.id == OWNER_ID` check. Guilds, channels, and roles are selected from Discord menus; the owner panel does not request numeric IDs.
- The owner dashboard controls feature and command toggles, moderation, tickets, messages, verification, log categories, per-guild activity, maintenance, reset, and double-confirmed leave. All sends and moderation actions check the bot's effective Discord permissions.
- Welcome text and preview are configurable in the panel, but automatic welcome messages remain disabled.
- Warning records and guild settings are stored in local JSON files under `data/`.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
