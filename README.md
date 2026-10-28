# Discord Slash-Command Bot

A small `discord.py` bot with two global slash commands:

- `/ping` replies with a pong and the bot's Discord gateway latency.
- `/help` shows the available commands privately.

## Configure and run

1. Create a Discord application and bot in the Discord Developer Portal.
2. Invite the bot to your server with the `bot` and `applications.commands` OAuth2 scopes.
3. Add the bot token to Replit Secrets as `DISCORD_TOKEN`. Do not commit the token or put it in source files.
4. Start the **Discord Bot** workflow, or run `uv run discord-bot`.

The bot only needs the default guild intent for interactions; message-content access is not enabled. Global slash commands can take some time to appear after the first sync.
