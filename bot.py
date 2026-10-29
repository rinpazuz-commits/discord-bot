
import discord
from discord.ext import commands
import random

# ================== CONFIG ==================
TOKEN = "MTU0ODY4MjI3MTMwODEyODM2OQ.GsAzMX.MUzYJR6myR1Ff4o-Z3CziGz0HCv7E9E0Jyz8nE"

TRIGGER_WORDS = [
    "app",
    "style",
    "boom",
    # ajoute d'autres mots ici
]

WHOLE_WORD_ONLY = True

# Réponses du 8ball (en anglais)
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
    "Signs point to yes",
    "Outlook not so good",
]
# ============================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

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
    print(f"Connecté en tant que {bot.user} (ID: {bot.user.id})")
    print("Bot prêt (Style + 8ball + Reply support)")
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
        return  # on arrête ici, pas de style/webhook

    # ========== STYLE / WEBHOOK ==========
    if not contains_trigger(content):
        await bot.process_commands(message)
        return

    if not message.channel.permissions_for(message.guild.me).manage_messages:
        return

    try:
        reference = None
        if message.reference and message.reference.message_id:
            reference = discord.MessageReference(
                message_id=message.reference.message_id,
                channel_id=message.channel.id,
                guild_id=message.guild.id
            )

        await message.delete()

        webhook = await get_webhook(message.channel)

        await webhook.send(
            content=message.content,
            username=message.author.display_name,
            avatar_url=message.author.display_avatar.url,
            reference=reference,
            wait=True
        )

    except discord.Forbidden:
        print(f"Permissions manquantes dans #{message.channel.name}")
    except Exception as e:
        print(f"Erreur : {e}")

    await bot.process_commands(message)

# ===== Commandes admin =====
@bot.command()
@commands.has_permissions(administrator=True)
async def addtrigger(ctx, *, word: str):
    """Ajoute un mot déclencheur"""
    word = word.lower().strip()
    if word not in [w.lower() for w in TRIGGER_WORDS]:
        TRIGGER_WORDS.append(word)
        await ctx.send(f"✅ Mot ajouté : `{word}`")
    else:
        await ctx.send("Ce mot est déjà dans la liste.")

@bot.command()
@commands.has_permissions(administrator=True)
async def removetrigger(ctx, *, word: str):
    """Supprime un mot déclencheur"""
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
    """Affiche la liste des mots déclencheurs"""
    if not TRIGGER_WORDS:
        await ctx.send("Aucun mot déclencheur.")
        return
    await ctx.send("**Mots déclencheurs actuels :**\n" + "\n".join(f"• `{w}`" for w in TRIGGER_WORDS))

bot.run(TOKEN)
