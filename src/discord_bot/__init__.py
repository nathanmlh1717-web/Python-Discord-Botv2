"""Discord slash-command bot."""

from __future__ import annotations

import asyncio
import logging
import os

import discord
from discord.ext import commands

LOGGER = logging.getLogger("discord_bot")


class SlashCommandBot(commands.Bot):
    """Bot that registers its global application commands when it starts."""

    async def setup_hook(self) -> None:
        synced_commands = await self.tree.sync()
        LOGGER.info("Synced %d global slash command(s).", len(synced_commands))


def create_bot() -> SlashCommandBot:
    """Create the bot and register its slash commands."""
    bot = SlashCommandBot(
        command_prefix=commands.when_mentioned,
        intents=discord.Intents.default(),
    )

    @bot.tree.command(name="ping", description="Check whether the bot is responding.")
    async def ping(interaction: discord.Interaction) -> None:
        latency_ms = round(bot.latency * 1000)
        await interaction.response.send_message(
            f"Pong! Gateway latency: {latency_ms} ms."
        )

    @bot.tree.command(name="help", description="Show the available bot commands.")
    async def help_command(interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Available commands",
            description="Use one of these slash commands:",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="/ping",
            value="Check whether the bot is responding and see its gateway latency.",
            inline=False,
        )
        embed.add_field(
            name="/help",
            value="Show this command list.",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    return bot


async def _run_bot(token: str) -> None:
    bot = create_bot()
    async with bot:
        await bot.start(token)


def main() -> None:
    """Start the bot using the DISCORD_TOKEN environment variable."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit(
            "DISCORD_TOKEN is not set. Add it as a Replit Secret before starting the bot."
        )

    asyncio.run(_run_bot(token))
