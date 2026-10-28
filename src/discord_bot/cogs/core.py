from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord_bot import SlashCommandBot


class CoreCog(commands.Cog):
    def __init__(self, bot: SlashCommandBot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Afficher la latence du bot.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong ! Latence de la passerelle : {latency_ms} ms.")

    @app_commands.command(name="help", description="Afficher la liste des commandes du bot.")
    async def help_command(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Commandes du bot",
            description="Les commandes sensibles nécessitent les permissions adaptées.",
            color=discord.Color.blurple(),
        )
        sections = (
            (
                "Modération",
                "/ban · /kick · /timeout · /untimeout · /warn · /warnings\n"
                "/clear · /slowmode · /lock · /unlock",
            ),
            (
                "Informations",
                "/userinfo · /serverinfo · /avatar · /botinfo · /ping",
            ),
            (
                "Utilitaires",
                "/say · /embed · /poll · /announce · /suggest · /report",
            ),
            (
                "Staff et configuration",
                "/stafflist · /logsetup · /ticketsetup · /verifysetup",
            ),
        )
        for name, value in sections:
            embed.add_field(name=name, value=value, inline=False)
        if interaction.user.id == self.bot.owner_id:
            embed.add_field(
                name="Propriétaire du bot",
                value=(
                    "/owner-servers · /owner-serverinfo · /owner-send · /owner-config\n"
                    "/owner-leave · /owner-disable · /owner-enable"
                ),
                inline=False,
            )
        embed.set_footer(text="Utilisez /help pour retrouver cette liste.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
