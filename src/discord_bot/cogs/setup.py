from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.common import log_action, verification_role_error
from discord_bot.views import TicketPanelView, VerifyView

if TYPE_CHECKING:
    from discord_bot import SlashCommandBot

class SetupCog(commands.Cog):
    def __init__(self, bot: SlashCommandBot) -> None:
        self.bot = bot

    @app_commands.command(name="logsetup", description="Configurer le salon des journaux du bot.")
    @app_commands.describe(channel="Salon où envoyer les logs de modération et de tickets")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logsetup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Cette commande doit être utilisée sur un serveur.",
                ephemeral=True,
            )
            return
        bot_member = guild.me
        if bot_member is None:
            await interaction.response.send_message(
                "Impossible de vérifier les permissions du bot.",
                ephemeral=True,
            )
            return
        permissions = channel.permissions_for(bot_member)
        if not permissions.view_channel or not permissions.send_messages or not permissions.embed_links:
            await interaction.response.send_message(
                "Le bot doit pouvoir voir ce salon, y envoyer des messages et intégrer des liens.",
                ephemeral=True,
            )
            return
        await self.bot.config_store.set_guild_values(
            guild.id,
            log_channel_id=channel.id,
        )
        await interaction.response.send_message(
            f"Les journaux du bot seront envoyés dans {channel.mention}.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="ticketsetup", description="Installer le panneau privé de création de tickets.")
    @app_commands.describe(staff_role="Rôle qui pourra voir et traiter les tickets")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def ticketsetup(
        self,
        interaction: discord.Interaction,
        staff_role: discord.Role,
    ) -> None:
        guild = interaction.guild
        channel = interaction.channel
        if guild is None or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Cette commande doit être utilisée dans un salon textuel de serveur.",
                ephemeral=True,
            )
            return
        bot_member = guild.me
        if bot_member is None:
            await interaction.response.send_message(
                "Impossible de vérifier les permissions du bot.",
                ephemeral=True,
            )
            return
        if staff_role.is_default() or staff_role >= bot_member.top_role:
            await interaction.response.send_message(
                "Choisissez un rôle de staff attribuable et inférieur au rôle le plus élevé du bot.",
                ephemeral=True,
            )
            return

        config = await self.bot.config_store.get_guild(guild.id)
        category_id = config.get("ticket_category_id")
        category = guild.get_channel(int(category_id)) if category_id else None
        if category is not None and not isinstance(category, discord.CategoryChannel):
            category = None
        if category is None:
            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                category = await guild.create_category(
                    "Tickets",
                    reason=f"Configuration des tickets par {interaction.user}",
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "Le bot ne peut pas créer de catégorie. Vérifiez sa permission `Gérer les salons`.",
                    ephemeral=True,
                )
                return
            except discord.HTTPException:
                await interaction.followup.send(
                    "Discord n'a pas pu créer la catégorie des tickets.",
                    ephemeral=True,
                )
                return
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)

        embed = discord.Embed(
            title="Besoin d'aide ?",
            description=(
                "Notre équipe est là pour vous aider. Ouvrez un ticket privé et "
                "expliquez votre demande ; seul vous et le staff pourront le consulter."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Comment ça marche",
            value="Cliquez sur le bouton ci-dessous. Un salon privé sera créé pour votre demande.",
            inline=False,
        )
        embed.set_footer(text=f"Support · {guild.name}")
        view = TicketPanelView()
        try:
            panel_message = await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            await interaction.followup.send(
                "Le bot ne peut pas publier le panneau dans ce salon.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Discord n'a pas pu publier le panneau de tickets.",
                ephemeral=True,
            )
            return

        await self.bot.config_store.set_guild_values(
            guild.id,
            staff_role_id=staff_role.id,
            ticket_category_id=category.id,
        )
        self.bot.add_view(view, message_id=panel_message.id)
        await log_action(
            self.bot,
            guild,
            "Panneau de tickets installé",
            f"Salon : {channel.mention}\nRôle du staff : {staff_role.mention}",
            color=discord.Color.blurple(),
        )
        await interaction.followup.send(
            f"Panneau de tickets publié dans {channel.mention}. Catégorie privée : {category.mention}.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="verifysetup", description="Publier un panneau de vérification par rôle.")
    @app_commands.describe(role="Rôle non sensible attribué après vérification")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True, send_messages=True, embed_links=True)
    async def verifysetup(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        guild = interaction.guild
        channel = interaction.channel
        if guild is None or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Cette commande doit être utilisée dans un salon textuel de serveur.",
                ephemeral=True,
            )
            return
        bot_member = guild.me
        if bot_member is None:
            await interaction.response.send_message(
                "Impossible de vérifier les permissions du bot.",
                ephemeral=True,
            )
            return
        role_error = verification_role_error(role, bot_member)
        if role_error:
            await interaction.response.send_message(
                role_error,
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Vérification du serveur",
            description=(
                "Cliquez sur **Se vérifier** pour confirmer votre arrivée et obtenir "
                f"le rôle {role.mention}."
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text=guild.name)
        view = VerifyView(role.id)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            panel_message = await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            await interaction.followup.send(
                "Le bot ne peut pas publier le panneau dans ce salon.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Discord n'a pas pu publier le panneau de vérification.",
                ephemeral=True,
            )
            return

        config = await self.bot.config_store.get_guild(guild.id)
        previous_role_ids = config.get("verification_role_ids", [])
        if not isinstance(previous_role_ids, list):
            previous_role_ids = []
        role_ids = sorted({int(value) for value in previous_role_ids if str(value).isdigit()} | {role.id})
        await self.bot.config_store.set_guild_values(
            guild.id,
            verification_role_id=role.id,
            verification_role_ids=role_ids,
        )
        self.bot.add_view(view, message_id=panel_message.id)
        await interaction.followup.send(
            f"Panneau de vérification publié dans {channel.mention}.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="stafflist", description="Afficher les membres du rôle de staff configuré.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def stafflist(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Cette commande doit être utilisée sur un serveur.",
                ephemeral=True,
            )
            return
        config = await self.bot.config_store.get_guild(guild.id)
        role_id = config.get("staff_role_id")
        role = guild.get_role(int(role_id)) if role_id else None
        if role is None:
            await interaction.response.send_message(
                "Aucun rôle de staff n'est configuré. Utilisez `/ticketsetup` pour le définir.",
                ephemeral=True,
            )
            return

        members = sorted(role.members, key=lambda member: member.display_name.casefold())
        embed = discord.Embed(
            title=f"Équipe du serveur · {role.name}",
            description=(
                "\n".join(member.mention for member in members[:50])
                if members
                else "Aucun membre du staff n'est actuellement chargé."
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"{len(members)} membre(s) en cache")
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
