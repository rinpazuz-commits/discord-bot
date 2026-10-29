import discord
from discord.ext import commands
import random
import json
import os
import re
from pathlib import Path
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ================== CONFIG ==================
TOKEN = os.getenv("TOKEN")
TRIGGER_FILE = Path(__file__).with_name("trigger.json")
DEFAULT_TRIGGER_WORDS = ["app", "style", "boom"]
WHOLE_WORD_ONLY = True

EIGHTBALL_RESPONSES = [
    "Yes",
    "No",
    "Idk",
    "Ask our lord and savior Diane",
    "Maybe",
    "Absolutely",
    "Hell no",
    "The universe says yes",
    "Don't count on it",
]


def load_trigger_words():
    """Load trigger words from trigger.json; use defaults if the file is missing/invalid."""
    try:
        with TRIGGER_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        # Supports either a simple JSON list or {"triggers": [...]}.
        if isinstance(data, dict):
            data = data.get("triggers", data.get("trigger_words", []))

        if not isinstance(data, list):
            raise ValueError("trigger.json must contain a JSON list of words")

        words = [
            str(word).strip().lower()
            for word in data
            if isinstance(word, (str, int, float)) and str(word).strip()
        ]
        if not words:
            raise ValueError("trigger.json contains no trigger words")

        print(f"{len(words)} mot(s) déclencheur(s) chargé(s) depuis trigger.json")
        return list(dict.fromkeys(words))
    except FileNotFoundError:
        print("trigger.json introuvable : utilisation des mots par défaut.")
    except (json.JSONDecodeError, OSError, ValueError) as error:
        print(f"Erreur lecture trigger.json : {error}. Utilisation des mots par défaut.")

    return DEFAULT_TRIGGER_WORDS.copy()


TRIGGER_WORDS = load_trigger_words()


def save_trigger_words():
    """Persist changes made by !addtrigger and !removetrigger."""
    with TRIGGER_FILE.open("w", encoding="utf-8") as file:
        json.dump(TRIGGER_WORDS, file, ensure_ascii=False, indent=2)
        file.write("\n")


# ================== RENDER HTTP SERVER ==================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"Discord bot service is running."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def run_web_server():
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Serveur HTTP actif sur le port {port}")
    server.serve_forever()


# ================== DISCORD BOT ==================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
webhook_cache = {}


async def get_webhook(channel: discord.TextChannel) -> discord.Webhook:
    if channel.id in webhook_cache:
        return webhook_cache[channel.id]

    webhooks = await channel.webhooks()
    for webhook in webhooks:
        if webhook.user and bot.user and webhook.user.id == bot.user.id:
            webhook_cache[channel.id] = webhook
            return webhook

    webhook = await channel.create_webhook(name="StyleBot")
    webhook_cache[channel.id] = webhook
    return webhook


def contains_trigger(content: str) -> bool:
    content_lower = content.lower()
    for trigger in TRIGGER_WORDS:
        trigger = trigger.strip().lower()
        if not trigger:
            continue
        if WHOLE_WORD_ONLY:
            # Recognizes punctuation around a word and supports multi-word triggers.
            pattern = rf"(?<!\\w){re.escape(trigger)}(?!\\w)"
            if re.search(pattern, content_lower):
                return True
        elif trigger in content_lower:
            return True
    return False


@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")
    print(f"{len(TRIGGER_WORDS)} mot(s) déclencheur(s) actif(s)")
    print("Bot prêt")
    print("------")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    content = message.content.strip()
    content_lower = content.lower()

    # ========== 8BALL ==========
    if content_lower.startswith("8ball"):
        response = random.choice(EIGHTBALL_RESPONSES)
        await message.reply(response)
        return

    # Don't replace admin commands; let them run normally.
    if content_lower.startswith("!"):
        await bot.process_commands(message)
        return

    # ========== STYLE / WEBHOOK ==========
    if not contains_trigger(content):
        await bot.process_commands(message)
        return

    print(f"Mot déclencheur détecté dans le message de {message.author}")

    try:
        webhook = await get_webhook(message.channel)
        # Send first: if sending fails, the original message remains intact.
        await webhook.send(
            content=message.content,
            username=message.author.display_name,
            avatar_url=message.author.display_avatar.url,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, users=True, roles=False, replied_user=False
            ),
            wait=True,
        )
        print("Message reposté avec succès")
        await message.delete()
        print("Message original supprimé")
    except discord.Forbidden as error:
        print(f"Permissions Discord insuffisantes pour remplacer le message : {error}")
    except Exception as error:
        print(f"ERREUR STYLE : {type(error).__name__} → {error}")
        import traceback
        traceback.print_exc()

    await bot.process_commands(message)


# ================== ADMIN COMMANDS ==================
@bot.command()
@commands.has_permissions(administrator=True)
async def addtrigger(ctx, *, word: str):
    word = word.lower().strip()
    if not word:
        await ctx.send("Indique un mot à ajouter.")
        return

    if word not in TRIGGER_WORDS:
        TRIGGER_WORDS.append(word)
        try:
            save_trigger_words()
            await ctx.send(f"✅ Mot ajouté et sauvegardé : `{word}`")
        except OSError as error:
            TRIGGER_WORDS.remove(word)
            await ctx.send(f"❌ Impossible de sauvegarder trigger.json : {error}")
    else:
        await ctx.send("Ce mot est déjà dans la liste.")


@bot.command()
@commands.has_permissions(administrator=True)
async def removetrigger(ctx, *, word: str):
    word = word.lower().strip()
    if word in TRIGGER_WORDS:
        TRIGGER_WORDS.remove(word)
        try:
            save_trigger_words()
            await ctx.send(f"✅ Mot supprimé et sauvegardé : `{word}`")
        except OSError as error:
            TRIGGER_WORDS.append(word)
            await ctx.send(f"❌ Impossible de sauvegarder trigger.json : {error}")
    else:
        await ctx.send("Ce mot n'était pas dans la liste.")


@bot.command()
@commands.has_permissions(administrator=True)
async def triggers(ctx):
    words = "\n".join(f"• `{word}`" for word in TRIGGER_WORDS)
    await ctx.send("**Mots déclencheurs :**\n" + (words or "Aucun"))


# ================== START ==================
if __name__ == "__main__":
    Thread(target=run_web_server, daemon=True).start()
    if not TOKEN:
        raise RuntimeError("La variable d'environnement TOKEN est absente.")
    bot.run(TOKEN)
