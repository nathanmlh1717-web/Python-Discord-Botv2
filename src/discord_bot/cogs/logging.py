from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from discord_bot.common import log_action

if TYPE_CHECKING:
    from discord_bot import SlashCommandBot


class LoggingCog(commands.Cog):
    def __init__(self, bot: SlashCommandBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        await log_action(
            self.bot,
            message.guild,
            "Message supprimé",
            f"Auteur : {message.author.mention} (`{message.author.id}`)\n"
            f"Salon : {message.channel.mention}\nID du message : `{message.id}`",
            color=discord.Color.orange(),
            category="messages",
            event_kind="message",
            actor_id=message.author.id,
        )

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if not messages:
            return
        guild = messages[0].guild
        if guild is None:
            return
        channel = messages[0].channel
        await log_action(
            self.bot,
            guild,
            "Messages supprimés en masse",
            f"Salon : {getattr(channel, 'mention', 'inconnu')}\n"
            f"Nombre supprimé : **{len(messages)}**",
            color=discord.Color.orange(),
            category="messages",
            event_kind="message",
        )
