import os
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import discord
from discord.ext import commands
from dotenv import load_dotenv

# ================== CONFIG ==================
load_dotenv()  # lit le fichier .env situé dans le même dossier
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "Aucun token trouvé. Crée un fichier .env à côté de bot.py "
        "contenant la ligne : DISCORD_TOKEN=ton_token_ici"
    )

# Fichier où la liste des mots déclencheurs est sauvegardée entre les redémarrages
TRIGGERS_FILE = "triggers.json"

# Liste par défaut, utilisée seulement si triggers.json n'existe pas encore
DEFAULT_TRIGGER_WORDS = [
    "app",
    "style",
    "boom",
]


def load_triggers() -> list[str]:
    if os.path.exists(TRIGGERS_FILE):
        try:
            with open(TRIGGERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except (json.JSONDecodeError, OSError) as e:
            print(f"Impossible de lire {TRIGGERS_FILE} ({e}), utilisation de la liste par défaut.")
    return list(DEFAULT_TRIGGER_WORDS)


def save_triggers(words: list[str]) -> None:
    with open(TRIGGERS_FILE, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)


TRIGGER_WORDS = load_triggers()

# True = only triggers on whole words (recommended)
# False = triggers even if the word is inside another word
WHOLE_WORD_ONLY = True
# ============================================


# ============= SERVEUR WEB (pour Render) =============
# Render ne garde en vie que des "Web Services" qui répondent au trafic HTTP.
# Ce petit serveur ne fait qu'attendre les pings d'UptimeRobot pour que Render
# ne mette jamais le bot en veille. Il n'a rien à voir avec Discord lui-même.
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot en ligne.")

    def log_message(self, format, *args):
        pass  # évite de polluer les logs avec chaque ping


def start_ping_server():
    port = int(os.environ.get("PORT", 8080))  # Render fournit ce port automatiquement
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    server.serve_forever()


threading.Thread(target=start_ping_server, daemon=True).start()
# =======================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Cache webhooks so we don't create a new one every message
webhook_cache = {}


async def get_webhook(channel: discord.TextChannel) -> discord.Webhook:
    # On ne fait plus confiance aveuglément au cache : si le webhook a été
    # supprimé manuellement sur Discord entre-temps, il faut le détecter ici
    # plutôt que de planter plus tard au moment de l'envoi.
    if channel.id in webhook_cache:
        cached = webhook_cache[channel.id]
        try:
            # Une requête légère qui échoue si le webhook n'existe plus
            await cached.fetch()
            return cached
        except discord.NotFound:
            del webhook_cache[channel.id]

    webhooks = await channel.webhooks()
    for wh in webhooks:
        if wh.user and wh.user.id == bot.user.id:
            webhook_cache[channel.id] = wh
            return wh

    # Discord limite à 15 webhooks par salon : si on en a trop (ex. d'anciens
    # redéploiements qui en ont recréé sans nettoyer), on réutilise le premier
    # qu'on trouve plutôt que d'échouer à la création.
    if len(webhooks) >= 15:
        raise RuntimeError(
            f"Limite de 15 webhooks atteinte sur #{channel.name} — "
            "supprime les anciens webhooks inutilisés dans les paramètres du salon."
        )

    wh = await channel.create_webhook(name="StyleBot")
    webhook_cache[channel.id] = wh
    return wh


def contains_trigger(content: str) -> bool:
    content_lower = content.lower()
    if WHOLE_WORD_ONLY:
        words = content_lower.split()
        return any(trigger.lower() in words for trigger in TRIGGER_WORDS)
    else:
        return any(trigger.lower() in content_lower for trigger in TRIGGER_WORDS)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Style/repost bot is ready.")
    print(f"[debug] Mots déclencheurs chargés : {TRIGGER_WORDS}")
    print("------")


@bot.event
async def on_message(message: discord.Message):
    # [debug] Log temporaire : affiche chaque message reçu par le bot, pour
    # vérifier qu'il reçoit bien le contenu et confirmer les mots déclencheurs.
    print(f"[debug] Message reçu dans #{getattr(message.channel, 'name', '?')} "
          f"de {message.author} : {message.content!r}")

    # Ignore bots and DMs
    if message.author.bot or not message.guild:
        return

    if not contains_trigger(message.content):
        print(f"[debug] Aucun trigger détecté (triggers actuels: {TRIGGER_WORDS})")
        await bot.process_commands(message)
        return

    print(f"[debug] Trigger détecté dans le message : {message.content!r}")

    # Check if bot has permission to manage messages
    if not message.channel.permissions_for(message.guild.me).manage_messages:
        print(f"[debug] BLOQUÉ : pas la permission 'Gérer les messages' dans #{message.channel.name}")
        return

    try:
        # On envoie D'ABORD via webhook, et on ne supprime le message original
        # QUE si ça a réussi. Avant, le message était supprimé en premier :
        # en cas d'échec de l'envoi (webhook supprimé, limite atteinte, rate
        # limit...), le contenu original disparaissait pour de bon sans être
        # remplacé. Maintenant, un échec laisse le message intact.
        webhook = await get_webhook(message.channel)

        await webhook.send(
            content=message.content,
            username=message.author.display_name,
            avatar_url=message.author.display_avatar.url,
            wait=True
        )

        await message.delete()

    except discord.Forbidden:
        print(f"[trigger] Permissions manquantes dans #{message.channel.name}")
    except discord.HTTPException as e:
        print(f"[trigger] Échec de l'envoi webhook dans #{message.channel.name}: {e}")
    except Exception as e:
        print(f"[trigger] Erreur inattendue dans #{message.channel.name}: {e}")

    await bot.process_commands(message)


# ===== Admin commands =====
@bot.command()
@commands.has_permissions(administrator=True)
async def addtrigger(ctx, *, word: str):
    """Add a new trigger word"""
    word = word.lower().strip()
    if word not in [w.lower() for w in TRIGGER_WORDS]:
        TRIGGER_WORDS.append(word)
        save_triggers(TRIGGER_WORDS)
        await ctx.send(f"✅ Added trigger: `{word}` (sauvegardé)")
    else:
        await ctx.send("That word is already a trigger.")


@bot.command()
@commands.has_permissions(administrator=True)
async def removetrigger(ctx, *, word: str):
    """Remove a trigger word"""
    word = word.lower().strip()
    for i, w in enumerate(TRIGGER_WORDS):
        if w.lower() == word:
            TRIGGER_WORDS.pop(i)
            save_triggers(TRIGGER_WORDS)
            await ctx.send(f"✅ Removed trigger: `{word}` (sauvegardé)")
            return
    await ctx.send("That word was not in the list.")


@bot.command()
@commands.has_permissions(administrator=True)
async def triggers(ctx):
    """Show current trigger words"""
    if not TRIGGER_WORDS:
        await ctx.send("No trigger words set.")
        return
    await ctx.send("**Current triggers:**\n" + "\n".join(f"• `{w}`" for w in TRIGGER_WORDS))


if __name__ == "__main__":
    # Petit délai au démarrage : si le service redémarre en boucle (ex. après
    # un crash), ça évite d'enchaîner les tentatives de connexion à Discord
    # trop vite, ce qui peut aggraver un blocage Cloudflare temporaire (429 / 1015).
    import time
    time.sleep(10)
    bot.run(TOKEN)
