
import discord
from discord.ext import commands
import random
import os
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ================== CONFIG ==================
TOKEN = os.getenv("TOKEN")

TRIGGER_WORDS = [
    "app",
    "style",
    "boom",
]

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
# ============================================


# ================== RENDER HTTP SERVER ==================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Health check pour Render et UptimeRobot
        body = b"Discord bot service is running."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Evite de remplir les logs avec chaque ping
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

    try:
        webhooks = await channel.webhooks()

        for wh in webhooks:
            if wh.user and wh.user.id == bot.user.id:
                webhook_cache[channel.id] = wh
                return wh

        wh = await channel.create_webhook(name="StyleBot")
        webhook_cache[channel.id] = wh
        return wh

    except Exception as e:
        print(f"ERREUR création webhook : {e}")
        raise


def contains_trigger(content: str) -> bool:
    content_lower = content.lower()

    if WHOLE_WORD_ONLY:
        words = content_lower.split()
        return any(trigger.lower() in words for trigger in TRIGGER_WORDS)

    return any(trigger.lower() in content_lower for trigger in TRIGGER_WORDS)


@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")
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

    # ========== STYLE / WEBHOOK ==========
    if not contains_trigger(content):
        await bot.process_commands(message)
        return

    print(f"Mot déclencheur détecté dans le message de {message.author}")

    try:
        reference = None

        if message.reference and message.reference.message_id:
            reference = discord.MessageReference(
                message_id=message.reference.message_id,
                channel_id=message.channel.id,
                guild_id=message.guild.id
            )

        await message.delete()
        print("Message supprimé")

        webhook = await get_webhook(message.channel)
        print("Webhook récupéré")

        await webhook.send(
            content=message.content,
            username=message.author.display_name,
            avatar_url=message.author.display_avatar.url,
            reference=reference,
            wait=True
        )

        print("Message reposté avec succès")

    except Exception as e:
        print(f"ERREUR STYLE : {type(e).__name__} → {e}")
        import traceback
        traceback.print_exc()

    await bot.process_commands(message)


# ================== ADMIN COMMANDS ==================
@bot.command()
@commands.has_permissions(administrator=True)
async def addtrigger(ctx, *, word: str):
    word = word.lower().strip()

    if word not in [w.lower() for w in TRIGGER_WORDS]:
        TRIGGER_WORDS.append(word)
        await ctx.send(f"✅ Mot ajouté : `{word}`")
    else:
        await ctx.send("Ce mot est déjà dans la liste.")


@bot.command()
@commands.has_permissions(administrator=True)
async def removetrigger(ctx, *, word: str):
    word = word.lower().strip()

    for i, w in enumerate(TRIGGER_WORDS):
        if w.lower() == word:
            TRIGGER_WORDS.pop(i)
            await ctx.send(f"✅ Mot supprimé : `{word}`")
            return

    await ctx.send("Ce mot n'était pas dans la liste.")


@bot.command()
@commands.has_permissions(administrator=True)
async def triggers(ctx):
    await ctx.send(
        "**Mots déclencheurs :**\n"
        + "\n".join(f"• `{w}`" for w in TRIGGER_WORDS)
    )


# ================== START ==================
if __name__ == "__main__":
    # Le serveur HTTP tourne séparément du bot Discord.
    Thread(target=run_web_server, daemon=True).start()

    # Démarre le bot Discord comme avant.
    bot.run(TOKEN)
