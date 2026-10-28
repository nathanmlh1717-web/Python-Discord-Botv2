"""Persistent Discord buttons for verification and private support tickets."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import discord

from discord_bot.common import log_action

if TYPE_CHECKING:
    from discord_bot import SlashCommandBot

LOGGER = logging.getLogger("discord_bot")
OWNER_RE = re.compile(r"(?:^|;)owner_id=(\d+)(?:;|$)")
STATUS_RE = re.compile(r"(?:^|;)status=(open|closed)(?:;|$)")


def get_bot(interaction: discord.Interaction) -> SlashCommandBot:
    return interaction.client  # type: ignore[return-value]


class TicketPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ouvrir un ticket",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        custom_id="ticket:open:v1",
    )
    async def open_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[TicketPanelView],
    ) -> None:
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Les tickets sont disponibles uniquement sur un serveur.",
                ephemeral=True,
            )
            return

        bot = get_bot(interaction)
        config = await bot.config_store.get_guild(guild.id)
        staff_role_id = config.get("staff_role_id")
        staff_role = guild.get_role(int(staff_role_id)) if staff_role_id else None
        if staff_role is None:
            await interaction.response.send_message(
                "Le système de tickets n'est pas configuré. Demandez au staff d'utiliser `/ticketsetup`.",
                ephemeral=True,
            )
            return

        for channel in guild.text_channels:
            topic = channel.topic or ""
            owner_match = OWNER_RE.search(topic)
            status_match = STATUS_RE.search(topic)
            if (
                owner_match
                and int(owner_match.group(1)) == member.id
                and status_match
                and status_match.group(1) == "open"
            ):
                await interaction.response.send_message(
                    f"Vous avez déjà un ticket ouvert : {channel.mention}",
                    ephemeral=True,
                )
                return

        bot_member = guild.me
        if bot_member is None:
            await interaction.response.send_message(
                "Impossible de vérifier les permissions du bot sur ce serveur.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        category_id = config.get("ticket_category_id")
        category = guild.get_channel(int(category_id)) if category_id else None
        if category is not None and not isinstance(category, discord.CategoryChannel):
            category = None
        if category is None:
            try:
                category = await guild.create_category("Tickets")
                await bot.config_store.set_guild_values(
                    guild.id,
                    ticket_category_id=category.id,
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "Le bot ne peut pas créer la catégorie des tickets. Vérifiez sa permission `Gérer les salons`.",
                    ephemeral=True,
                )
                return
            except discord.HTTPException:
                await interaction.followup.send(
                    "Discord n'a pas pu créer la catégorie des tickets. Réessayez plus tard.",
                    ephemeral=True,
                )
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
            staff_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
            ),
        }
        slug = re.sub(r"[^a-z0-9-]+", "-", member.display_name.lower()).strip("-")[:40]
        channel_name = f"ticket-{slug or member.id}"
        topic = f"owner_id={member.id};status=open"
        try:
            ticket_channel = await guild.create_text_channel(
                channel_name,
                category=category,
                overwrites=overwrites,
                topic=topic,
                reason=f"Ticket ouvert par {member} ({member.id})",
            )
            welcome = discord.Embed(
                title="Votre demande de support",
                description=(
                    f"Bonjour {member.mention} ! Décrivez votre demande ci-dessous. "
                    "Un membre du staff vous répondra dès que possible.\n\n"
                    "Cliquez sur **Fermer le ticket** lorsque votre demande est résolue."
                ),
                color=discord.Color.blurple(),
            )
            await ticket_channel.send(
                content=member.mention,
                embed=welcome,
                view=TicketCloseView(),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Le bot ne peut pas créer le ticket. Vérifiez ses permissions de gestion et d'accès aux salons.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Discord n'a pas pu créer le ticket. Réessayez plus tard.",
                ephemeral=True,
            )
            return

        await log_action(
            bot,
            guild,
            "Ticket ouvert",
            f"Ticket : {ticket_channel.mention}\nMembre : {member.mention} (`{member.id}`)",
            color=discord.Color.green(),
        )
        await interaction.followup.send(
            f"Votre ticket est ouvert : {ticket_channel.mention}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class TicketCloseView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Fermer le ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:close:v1",
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[TicketCloseView],
    ) -> None:
        guild = interaction.guild
        channel = interaction.channel
        member = interaction.user
        if guild is None or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Ce bouton doit être utilisé dans un ticket.",
                ephemeral=True,
            )
            return
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Impossible d'identifier le membre.",
                ephemeral=True,
            )
            return

        owner_match = OWNER_RE.search(channel.topic or "")
        status_match = STATUS_RE.search(channel.topic or "")
        if not owner_match:
            await interaction.response.send_message(
                "Ce salon n'est pas reconnu comme un ticket.",
                ephemeral=True,
            )
            return
        if status_match and status_match.group(1) == "closed":
            await interaction.response.send_message(
                "Ce ticket est déjà fermé.",
                ephemeral=True,
            )
            return

        bot = get_bot(interaction)
        config = await bot.config_store.get_guild(guild.id)
        staff_role_id = config.get("staff_role_id")
        staff_role = guild.get_role(int(staff_role_id)) if staff_role_id else None
        ticket_owner_id = int(owner_match.group(1))
        is_staff = (
            member.guild_permissions.manage_channels
            or (staff_role is not None and staff_role in member.roles)
        )
        if member.id != ticket_owner_id and not is_staff:
            await interaction.response.send_message(
                "Seul l'auteur du ticket ou un membre du staff peut le fermer.",
                ephemeral=True,
            )
            return

        owner = guild.get_member(ticket_owner_id)
        if owner is None:
            owner = next(
                (
                    target
                    for target in channel.overwrites
                    if isinstance(target, discord.Member) and target.id == ticket_owner_id
                ),
                None,
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            if owner is not None:
                await channel.set_permissions(
                    owner,
                    view_channel=True,
                    send_messages=False,
                    add_reactions=False,
                    reason=f"Ticket fermé par {member} ({member.id})",
                )
            closed_name = channel.name
            if not closed_name.startswith("ferme-"):
                closed_name = f"ferme-{closed_name}"[:100]
            await channel.edit(
                name=closed_name,
                topic=f"owner_id={ticket_owner_id};status=closed",
                reason=f"Ticket fermé par {member} ({member.id})",
            )
            await channel.send(
                embed=discord.Embed(
                    title="Ticket fermé",
                    description=f"Fermé par {member.mention}. L'historique est conservé pour le staff.",
                    color=discord.Color.orange(),
                ),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Le bot n'a pas les permissions nécessaires pour fermer ce ticket.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Discord n'a pas pu fermer le ticket. Réessayez plus tard.",
                ephemeral=True,
            )
            return

        await log_action(
            bot,
            guild,
            "Ticket fermé",
            f"Salon : {channel.mention}\nAuteur : <@{ticket_owner_id}>\nFermé par : {member.mention}",
            color=discord.Color.orange(),
        )
        await interaction.followup.send(
            "Ticket fermé. Son historique reste accessible au staff.",
            ephemeral=True,
        )


class VerifyView(discord.ui.View):
    def __init__(self, role_id: int) -> None:
        super().__init__(timeout=None)
        self.role_id = role_id
        self.add_item(
            discord.ui.Button(
                label="Se vérifier",
                emoji="✅",
                style=discord.ButtonStyle.success,
                custom_id=f"verify:grant:{role_id}",
            )
        )

        self.children[0].callback = self._verify  # type: ignore[method-assign]

    async def _verify(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "La vérification est disponible uniquement sur un serveur.",
                ephemeral=True,
            )
            return
        role = guild.get_role(self.role_id)
        if role is None:
            await interaction.response.send_message(
                "Le rôle de vérification n'existe plus. Demandez au staff de relancer `/verifysetup`.",
                ephemeral=True,
            )
            return
        bot = get_bot(interaction)
        config = await bot.config_store.get_guild(guild.id)
        if int(config.get("verification_role_id", 0)) != self.role_id:
            await interaction.response.send_message(
                "Ce panneau de vérification n'est plus actif. Utilisez le panneau le plus récent.",
                ephemeral=True,
            )
            return
        if role in member.roles:
            await interaction.response.send_message(
                "Vous êtes déjà vérifié.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await member.add_roles(role, reason="Vérification via le panneau du serveur")
        except discord.Forbidden:
            await interaction.followup.send(
                "Le bot ne peut pas attribuer ce rôle. Vérifiez sa permission `Gérer les rôles` et la hiérarchie.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Discord n'a pas pu attribuer le rôle. Réessayez plus tard.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            f"Vérification terminée. Le rôle {role.mention} vous a été attribué.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
