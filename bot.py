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
    if channel.id in webhook_cache:
        return webhook_cache[channel.id]

    webhooks = await channel.webhooks()
    for wh in webhooks:
        if wh.user and wh.user.id == bot.user.id:
            webhook_cache[channel.id] = wh
            return wh

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
    print("------")


@bot.event
async def on_message(message: discord.Message):
    # Ignore bots and DMs
    if message.author.bot or not message.guild:
        return

    if not contains_trigger(message.content):
        await bot.process_commands(message)
        return

    # Check if bot has permission to manage messages
    if not message.channel.permissions_for(message.guild.me).manage_messages:
        return

    try:
        await message.delete()

        webhook = await get_webhook(message.channel)

        await webhook.send(
            content=message.content,
            username=message.author.display_name,
            avatar_url=message.author.display_avatar.url,
            wait=True
        )

    except discord.Forbidden:
        print(f"Missing permissions in #{message.channel.name}")
    except Exception as e:
        print(f"Error: {e}")

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


bot.run(TOKEN)
