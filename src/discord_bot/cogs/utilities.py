from __future__ import annotations

import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.common import log_action

if TYPE_CHECKING:
    from discord_bot import SlashCommandBot

POLL_EMOJIS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟")


class UtilitiesCog(commands.Cog):
    def __init__(self, bot: SlashCommandBot) -> None:
        self.bot = bot

    @app_commands.command(name="say", description="Faire envoyer un message par le bot.")
    @app_commands.describe(message="Texte à envoyer dans ce salon")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(send_messages=True)
    async def say(self, interaction: discord.Interaction, message: str) -> None:
        if len(message) > 2000:
            await interaction.response.send_message(
                "Le message ne peut pas dépasser 2 000 caractères.",
                ephemeral=True,
            )
            return
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "Cette commande doit être utilisée dans un salon textuel.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await channel.send(message, allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send("Message envoyé.", ephemeral=True)

    @app_commands.command(name="embed", description="Créer un embed personnalisé dans ce salon.")
    @app_commands.describe(
        title="Titre de l'embed",
        description="Texte de l'embed",
        color="Couleur hexadécimale, par exemple #5865F2",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
    async def embed_command(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        color: str = "#5865F2",
    ) -> None:
        if not 1 <= len(title) <= 256 or not 1 <= len(description) <= 4000:
            await interaction.response.send_message(
                "Le titre doit contenir de 1 à 256 caractères et le texte de 1 à 4 000 caractères.",
                ephemeral=True,
            )
            return
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            await interaction.response.send_message(
                "Couleur invalide. Utilisez le format hexadécimal `#5865F2`.",
                ephemeral=True,
            )
            return
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "Cette commande doit être utilisée dans un salon textuel.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color(int(color[1:], 16)),
        )
        await interaction.response.defer(ephemeral=True, thinking=True)
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send("Embed envoyé.", ephemeral=True)

    @app_commands.command(name="poll", description="Créer un sondage avec 2 à 10 choix.")
    @app_commands.describe(
        question="Question du sondage",
        options="Choix séparés par des virgules (2 à 10)",
    )
    @app_commands.checks.bot_has_permissions(
        send_messages=True,
        embed_links=True,
        add_reactions=True,
    )
    async def poll(self, interaction: discord.Interaction, question: str, options: str) -> None:
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "Cette commande doit être utilisée dans un salon textuel.",
                ephemeral=True,
            )
            return
        choices = [option.strip() for option in options.split(",") if option.strip()]
        if not 2 <= len(choices) <= 10 or any(len(option) > 80 for option in choices):
            await interaction.response.send_message(
                "Indiquez de 2 à 10 choix, séparés par des virgules (80 caractères maximum par choix).",
                ephemeral=True,
            )
            return
        if not 1 <= len(question) <= 250:
            await interaction.response.send_message(
                "La question doit contenir de 1 à 250 caractères.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="Sondage",
            description=f"**{question}**\n\n"
            + "\n".join(f"{POLL_EMOJIS[index]}  {option}" for index, option in enumerate(choices)),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Sondage lancé par {interaction.user.display_name}")
        await interaction.response.defer(ephemeral=True, thinking=True)
        message = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        for emoji in POLL_EMOJIS[: len(choices)]:
            await message.add_reaction(emoji)
        await interaction.followup.send("Sondage publié.", ephemeral=True)

    @app_commands.command(name="announce", description="Publier une annonce sous forme d'embed.")
    @app_commands.describe(
        title="Titre de l'annonce",
        message="Contenu de l'annonce",
        channel="Salon de destination (salon actuel par défaut)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def announce(
        self,
        interaction: discord.Interaction,
        title: str,
        message: str,
        channel: discord.TextChannel | None = None,
    ) -> None:
        guild = interaction.guild
        target = channel or interaction.channel
        if guild is None or not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "Choisissez un salon textuel de ce serveur.",
                ephemeral=True,
            )
            return
        if not 1 <= len(title) <= 256 or not 1 <= len(message) <= 4000:
            await interaction.response.send_message(
                "Le titre doit contenir de 1 à 256 caractères et le texte de 1 à 4 000 caractères.",
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
        permissions = target.permissions_for(bot_member)
        if not permissions.send_messages or not permissions.embed_links:
            await interaction.response.send_message(
                "Le bot ne peut pas envoyer d'embed dans ce salon.",
                ephemeral=True,
            )
            return
        announcement = discord.Embed(
            title=title,
            description=message,
            color=discord.Color.blurple(),
        )
        announcement.set_footer(text=f"Annonce de {interaction.user.display_name}")
        await interaction.response.defer(ephemeral=True, thinking=True)
        await target.send(embed=announcement, allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send(
            f"Annonce publiée dans {target.mention}.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="suggest", description="Publier une suggestion à voter.")
    @app_commands.describe(suggestion="Suggestion à soumettre à la communauté")
    async def suggest(self, interaction: discord.Interaction, suggestion: str) -> None:
        guild = interaction.guild
        current_channel = interaction.channel
        if guild is None or not isinstance(current_channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "Cette commande doit être utilisée dans un serveur.",
                ephemeral=True,
            )
            return
        if not 1 <= len(suggestion) <= 1500:
            await interaction.response.send_message(
                "La suggestion doit contenir de 1 à 1 500 caractères.",
                ephemeral=True,
            )
            return
        config = await self.bot.config_store.get_guild(guild.id)
        configured_channel_id = config.get("suggestion_channel_id")
        destination = (
            guild.get_channel(int(configured_channel_id))
            if configured_channel_id
            else current_channel
        )
        if not isinstance(destination, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "Le salon de suggestions configuré n'existe plus. Corrigez-le depuis `/owner` → Fonctionnalités.",
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
        permissions = destination.permissions_for(bot_member)
        can_send = (
            permissions.send_messages_in_threads
            if isinstance(destination, discord.Thread)
            else permissions.send_messages
        )
        if (
            not permissions.view_channel
            or not can_send
            or not permissions.embed_links
            or not permissions.add_reactions
        ):
            await interaction.response.send_message(
                "Le bot doit pouvoir voir ce salon, y envoyer des messages, intégrer des liens et ajouter des réactions.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="Nouvelle suggestion",
            description=suggestion,
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Proposée par {interaction.user.display_name}")
        await interaction.response.defer(ephemeral=True, thinking=True)
        message = await destination.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await message.add_reaction("👍")
        await message.add_reaction("👎")
        await interaction.followup.send(
            f"Votre suggestion a été publiée dans {destination.mention} et peut maintenant être votée.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="report", description="Signaler un membre à l'équipe du serveur.")
    @app_commands.describe(member="Membre à signaler", reason="Motif du signalement")
    async def report(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Cette commande doit être utilisée sur un serveur.",
                ephemeral=True,
            )
            return
        cleaned_reason = reason.strip()
        if not 1 <= len(cleaned_reason) <= 1000:
            await interaction.response.send_message(
                "Le motif doit contenir de 1 à 1 000 caractères.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel_name = getattr(interaction.channel, "mention", "salon inconnu")
        logged = await log_action(
            self.bot,
            guild,
            "Nouveau signalement",
            f"Membre signalé : {member.mention} (`{member.id}`)\n"
            f"Signalé par : {interaction.user.mention} (`{interaction.user.id}`)\n"
            f"Salon : {channel_name}\nMotif : {cleaned_reason}",
            color=discord.Color.red(),
        )
        if not logged:
            await interaction.followup.send(
                "Aucun salon de logs n'est configuré. Demandez à un administrateur d'utiliser `/logsetup`.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            "Votre signalement a été transmis au staff.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
