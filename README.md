# Bot Discord — commandes slash

Bot modulaire construit avec `discord.py`. Il comprend des commandes de modération, d'information et d'utilitaires, un système de tickets privés, une vérification par rôle et des journaux configurables.

## Démarrage

1. Créez l'application et le bot dans le [portail développeur Discord](https://discord.com/developers/applications).
2. Invitez-le sur le serveur avec les scopes OAuth2 `bot` et `applications.commands`.
3. Ajoutez le jeton comme Secret Replit nommé `DISCORD_TOKEN` et votre identifiant utilisateur Discord comme Secret `OWNER_ID`. Ne placez jamais ces valeurs dans le code.
4. Démarrez le workflow **Discord Bot**. Il exécute `uv run discord-bot`.
5. Dans Discord, utilisez `/logsetup` pour choisir le salon des journaux.
6. Utilisez `/ticketsetup` avec le rôle staff et `/verifysetup` avec le rôle non sensible à attribuer.

Accordez au bot uniquement les permissions nécessaires aux fonctionnalités voulues : voir les salons, envoyer des messages, intégrer des liens, lire l'historique, gérer les messages, gérer les salons, gérer les rôles, bannir, expulser, mettre en timeout et ajouter des réactions. Il n'a pas besoin de la permission Administrateur.

`/ticketsetup` crée la catégorie privée des tickets si elle n'existe pas. Les boutons restent actifs après un redémarrage. Fermer un ticket conserve son historique et retire à son auteur le droit d'écrire.

Les commandes de serveur sont synchronisées globalement au démarrage et peuvent prendre un peu de temps à apparaître. Les avertissements et la configuration par serveur sont stockés sous `data/`; ces fichiers sont exclus de Git.

Le bot n'active pas l'intent privilégié « Message Content ». Les messages envoyés et les embeds désactivent les mentions automatiques. Le rôle choisi dans `/verifysetup` est refusé s'il permet l'administration ou la modération.

## Commandes

- **Modération** : `/ban`, `/kick`, `/timeout`, `/untimeout`, `/warn`, `/warnings`, `/clear`, `/slowmode`, `/lock`, `/unlock`
- **Informations** : `/userinfo`, `/serverinfo`, `/avatar`, `/botinfo`, `/ping`, `/help`
- **Utilitaires** : `/say`, `/embed`, `/poll`, `/announce`, `/suggest`, `/report`
- **Staff et configuration** : `/stafflist`, `/logsetup`, `/ticketsetup`, `/verifysetup`
- **Propriétaire du bot** : `/owner` ouvre le centre de contrôle privé; les serveurs, salons, rôles et tickets se choisissent dans des menus Discord.

Les commandes sensibles vérifient les permissions Discord et la hiérarchie des rôles. Les erreurs affichées par le bot sont en français.

`/owner` et toutes les interactions de son panneau vérifient côté serveur que l'identifiant de l'utilisateur est exactement celui de `OWNER_ID`; elles ne sont pas autorisées sur la seule base de leur visibilité ou des permissions de serveur. Le panneau permet de gérer les commandes, la modération, les tickets, les messages, la vérification, les logs, les statistiques et le contrôle par serveur. Les opérations sensibles vérifient les permissions effectives du bot.

Le salon des suggestions est utilisé par `/suggest`. Le panneau permet de modifier et prévisualiser le message de bienvenue, mais l'envoi automatique reste désactivé.
