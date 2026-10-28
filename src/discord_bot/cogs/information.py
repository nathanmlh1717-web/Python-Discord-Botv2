from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from discord_bot import SlashCommandBot


class InformationCog(commands.Cog):
    def __init__(self, bot: SlashCommandBot) -> None:
        self.bot = bot

    @app_commands.command(name="userinfo", description="Afficher les informations d'un membre.")
    @app_commands.describe(member="Membre à consulter (vous-même par défaut)")
    async def userinfo(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        guild = interaction.guild
        target = member or interaction.user
        if guild is None or not isinstance(target, discord.Member):
            await interaction.response.send_message(
                "Cette commande doit être utilisée sur un serveur.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title=f"Informations sur {target.display_name}",
            color=target.color if target.color.value else discord.Color.blurple(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Nom", value=f"{target} ({target.mention})", inline=False)
        embed.add_field(name="ID", value=f"`{target.id}`", inline=True)
        embed.add_field(
            name="Compte créé",
            value=discord.utils.format_dt(target.created_at, style="D"),
            inline=True,
        )
        embed.add_field(
            name="A rejoint le serveur",
            value=(
                discord.utils.format_dt(target.joined_at, style="D")
                if target.joined_at
                else "Date inconnue"
            ),
            inline=True,
        )
        roles = [role.mention for role in reversed(target.roles) if role != guild.default_role]
        role_text = ", ".join(roles) if roles else "Aucun rôle"
        embed.add_field(name=f"Rôles ({len(roles)})", value=role_text[:1024], inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Afficher les informations du serveur.")
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Cette commande doit être utilisée sur un serveur.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Propriétaire", value=guild.owner.mention if guild.owner else "Inconnu")
        embed.add_field(name="Membres", value=str(guild.member_count or "Inconnu"))
        embed.add_field(name="Salons", value=str(len(guild.channels)))
        embed.add_field(name="Rôles", value=str(len(guild.roles)))
        embed.add_field(
            name="Créé le",
            value=discord.utils.format_dt(guild.created_at, style="D"),
            inline=False,
        )
        embed.set_footer(text=f"ID du serveur : {guild.id}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Afficher l'avatar d'un membre.")
    @app_commands.describe(member="Membre à consulter (vous-même par défaut)")
    async def avatar(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        target = member or interaction.user
        if not isinstance(target, (discord.Member, discord.User)):
            await interaction.response.send_message(
                "Impossible de trouver cet utilisateur.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title=f"Avatar de {target.display_name if isinstance(target, discord.Member) else target.name}",
            color=discord.Color.blurple(),
        )
        embed.set_image(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="botinfo", description="Afficher les informations du bot.")
    async def botinfo(self, interaction: discord.Interaction) -> None:
        user = self.bot.user
        if user is None:
            await interaction.response.send_message(
                "Le bot est encore en cours de démarrage.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(title="Informations du bot", color=discord.Color.blurple())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Nom", value=user.name)
        embed.add_field(name="Serveurs", value=str(len(self.bot.guilds)))
        embed.add_field(name="Version discord.py", value=discord.__version__)
        embed.add_field(
            name="Latence",
            value=f"{round(self.bot.latency * 1000)} ms",
        )
        embed.add_field(
            name="En ligne depuis",
            value=discord.utils.format_dt(self.bot.started_at, style="R"),
            inline=False,
        )
        await interaction.response.send_message(embed=embed)
