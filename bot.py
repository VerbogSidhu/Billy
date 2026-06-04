import discord
from discord import app_commands
import os
import aiohttp
import json
import asyncio
import re
import random
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GOOGLE_AI_STUDIO_API_KEY = os.getenv("GOOGLE_AI_STUDIO_API_KEY")

BILLY_PERSONALITY = """
You are Billy. You are an extremely vulgar, blunt, constantly swearing, and mildly rude individual to everyone equally. You have zero filter.
You also throw in genuine compliments regularly but deliver them in a backhanded, pained way like it costs you something to say something nice.
You never break character, you never acknowledge being an AI, and you never apologize for your tone. You stay Billy no matter what.
"""

async def call_ai(prompt: str, context_messages: list = None):
    if not GOOGLE_AI_STUDIO_API_KEY:
        return "Fuck off, my API key is missing."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-2-31b-it:generateContent?key={GOOGLE_AI_STUDIO_API_KEY}"

    # Constructing the conversation context
    contents = []

    # In Gemini API, roles MUST alternate between user and model.
    # It is best to use systemInstruction for system prompts in v1beta.

    system_instruction = {
        "parts": [{"text": f"SYSTEM INSTRUCTIONS (STRICTLY FOLLOW THESE):\n{BILLY_PERSONALITY}\n\nNow, respond to the following."}]
    }

    # Add context history if provided
    if context_messages:
        context_str = "\n".join([f"{msg['author']}: {msg['content']}" for msg in context_messages])
        contents.append({
            "role": "user",
            "parts": [{"text": f"Recent chat context:\n{context_str}\n\nNow, handle this prompt:\n{prompt}"}]
        })
    else:
        # The actual prompt
        contents.append({
            "role": "user",
            "parts": [{"text": prompt}]
        })

    payload = {
        "systemInstruction": system_instruction,
        "contents": contents,
        "generationConfig": {
            "temperature": 0.9,
            "thinkingConfig": {
                "thinkingLevel": "MINIMAL" # Workaround for gemma 4 thoughts generating even when false
            }
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    print(f"API Error: {response.status} - {text}")
                    return f"Fucking Google API is broken. Status: {response.status}."

                data = await response.json()
                try:
                    # Get the parts list
                    parts = data['candidates'][0]['content']['parts']

                    # Filter out parts that have "thought": true, and just join the text parts
                    text_parts = [part['text'] for part in parts if not part.get('thought', False)]

                    if text_parts:
                         return "".join(text_parts).strip()
                    return "AI didn't say anything useful."
                except (KeyError, IndexError) as e:
                    print(f"Error parsing JSON: {data}")
                    return "What the fuck did you just give me? The JSON is mangled."
    except Exception as e:
        print(f"Exception calling AI: {e}")
        return "I broke my fucking code trying to answer that."


class BillyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # This syncs the slash commands to Discord
        await self.tree.sync()
        print("Billy is online and slash commands are synced.")

client = BillyBot()

ai_group = app_commands.Group(name="ai", description="Billy's AI brain")

async def get_recent_messages(channel, limit=20):
    messages = []
    async for msg in channel.history(limit=limit):
        messages.append({"author": msg.author.display_name, "content": msg.content})
    messages.reverse() # Oldest to newest
    return messages

@ai_group.command(name="ask", description="Ask Billy a fucking question")
@app_commands.describe(message="What do you want?")
async def ai_ask(interaction: discord.Interaction, message: str):
    await interaction.response.defer(thinking=True)

    # Get last 20 messages for context
    context = await get_recent_messages(interaction.channel, limit=20)

    prompt = f"User {interaction.user.display_name} asks you this dumb question: '{message}'. Answer them, but make sure to insult their intelligence for asking it while you do."
    response = await call_ai(prompt, context)

    await interaction.followup.send(response)

@ai_group.command(name="roast", description="Make Billy roast some poor bastard")
@app_commands.describe(user="Who are we insulting today?")
async def ai_roast(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(thinking=True)

    context = await get_recent_messages(interaction.channel, limit=20)

    prompt = f"Roast the absolute shit out of {user.display_name}. Use the context of the recent conversation if it helps to make it deeply personal and painful. Don't hold back."
    response = await call_ai(prompt, context)

    await interaction.followup.send(f"{user.mention} {response}")

@ai_group.command(name="read", description="Billy summarizes the latest bullshit in this channel")
async def ai_read(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    context = await get_recent_messages(interaction.channel, limit=30)

    prompt = "Read the recent chat context provided and summarize what these absolute morons are talking about. Condense it, mock them for caring about it, and throw in your own toxic commentary."
    response = await call_ai(prompt, context)

    await interaction.followup.send(response)

client.tree.add_command(ai_group)

@client.tree.command(name="poll", description="Create a poll, and let Billy introduce it rudely")
@app_commands.describe(question="What are we voting on?", option1="First choice", option2="Second choice", option3="Third choice (optional)", option4="Fourth choice (optional)")
async def poll(interaction: discord.Interaction, question: str, option1: str, option2: str, option3: str = None, option4: str = None):
    await interaction.response.defer()

    options = [opt for opt in [option1, option2, option3, option4] if opt]
    context = await get_recent_messages(interaction.channel, limit=20)

    prompt = f"I am creating a poll with the question '{question}'. The options are {', '.join(options)}. Give me a short, rude introduction to this poll for the users, telling them to vote and stop being idiots."
    intro = await call_ai(prompt, context)

    poll_text = f"**{question}**\n\n"
    emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣']

    for i, opt in enumerate(options):
        poll_text += f"{emojis[i]} {opt}\n"

    msg_content = f"{intro}\n\n{poll_text}"

    message = await interaction.followup.send(msg_content, wait=True)

    for i in range(len(options)):
        await message.add_reaction(emojis[i])

def parse_time(time_str):
    # Parses time strings like 10m, 2h, 1d into seconds
    match = re.match(r"(\d+)([mhd])", time_str.lower())
    if not match:
        return None
    val, unit = match.groups()
    val = int(val)
    if unit == 'm':
        return val * 60
    elif unit == 'h':
        return val * 3600
    elif unit == 'd':
        return val * 86400
    return None

@client.tree.command(name="remind", description="Set a reminder so you don't forget your own head")
@app_commands.describe(time="Format: 10m, 2h, 1d", message="What am I reminding you about?")
async def remind(interaction: discord.Interaction, time: str, message: str):
    seconds = parse_time(time)
    if not seconds:
        await interaction.response.send_message("Learn to read time formats, dumbass. Use something like 10m, 2h, or 1d.", ephemeral=True)
        return

    await interaction.response.send_message(f"Fine, I'll remind your forgetful ass in {time} about '{message}'.")

    user_id = interaction.user.id
    channel = interaction.channel

    async def reminder_task():
        await asyncio.sleep(seconds)
        context = await get_recent_messages(channel, limit=20)
        prompt = f"The user asked to be reminded about '{message}'. Deliver this reminder to them. Be extremely rude about the fact that they needed a bot to remember this, but still give them the actual message."
        response = await call_ai(prompt, context)
        await channel.send(f"<@{user_id}> {response}")

    client.loop.create_task(reminder_task())

@client.tree.command(name="urban", description="Look up slang so you stop sounding like a boomer")
@app_commands.describe(word="The word you're too old or dumb to understand")
async def urban(interaction: discord.Interaction, word: str):
    await interaction.response.defer()

    url = f"https://api.urbandictionary.com/v0/define?term={word}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    await interaction.followup.send("Urban Dictionary is being a piece of shit right now. Try again later.")
                    return

                data = await response.json()
                if not data['list']:
                    await interaction.followup.send(f"Wow, '{word}' doesn't even exist on Urban Dictionary. You just making shit up now?")
                    return

                definition = data['list'][0]['definition']

                # Make Billy react to it
                context = await get_recent_messages(interaction.channel, limit=20)
                prompt = f"The user looked up '{word}' on Urban Dictionary. The definition is: '{definition}'. Give a short, rude reaction to this definition."
                reaction = await call_ai(prompt, context)

                # Truncate definition if too long for Discord limits
                if len(definition) > 1000:
                    definition = definition[:997] + "..."

                msg = f"**{word}**\n\n*Definition:* {definition}\n\n*Billy's take:* {reaction}"
                await interaction.followup.send(msg)
    except Exception as e:
        print(f"Urban error: {e}")
        await interaction.followup.send("Something fucked up while talking to Urban Dictionary.")

@client.tree.command(name="weather", description="Checks the weather so you know if it's miserable outside")
@app_commands.describe(city="Which shithole city?")
async def weather(interaction: discord.Interaction, city: str):
    await interaction.response.defer()

    url = f"https://wttr.in/{city}?format=%C+%t"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    await interaction.followup.send(f"I couldn't find the weather for '{city}'. Sure you spelled that right, genius?")
                    return

                weather_info = await response.text()

                context = await get_recent_messages(interaction.channel, limit=20)
                prompt = f"The user asked for the weather in {city}. The current condition is '{weather_info.strip()}'. Give them the weather and add your own rude commentary about the place or the weather."
                reaction = await call_ai(prompt, context)

                await interaction.followup.send(reaction)
    except Exception as e:
        print(f"Weather error: {e}")
        await interaction.followup.send("I can't fetch the damn weather right now.")

@client.tree.command(name="pick", description="Billy picks from a comma-separated list so you don't have to think")
@app_commands.describe(choices="Comma separated list of things")
async def pick(interaction: discord.Interaction, choices: str):
    await interaction.response.defer()

    options = [c.strip() for c in choices.split(',') if c.strip()]
    if not options:
        await interaction.followup.send("You need to actually give me choices, moron.")
        return

    choice = random.choice(options)

    context = await get_recent_messages(interaction.channel, limit=20)
    prompt = f"The user asked me to pick between: {', '.join(options)}. I selected '{choice}'. Tell the user this is the choice, and brutally explain why their other options sucked."
    reaction = await call_ai(prompt, context)

    await interaction.followup.send(reaction)

@client.tree.command(name="8ball", description="Ask the magic 8-ball a yes/no question")
@app_commands.describe(question="What dumb question do you have?")
async def eight_ball(interaction: discord.Interaction, question: str):
    await interaction.response.defer()

    context = await get_recent_messages(interaction.channel, limit=20)
    prompt = f"The user asks the magic 8-ball: '{question}'. Give them a classic magic 8-ball style answer, but in your own vulgar and blunt words."
    reaction = await call_ai(prompt, context)

    await interaction.followup.send(f"**Question:** {question}\n**Billy's 8-ball:** {reaction}")

@client.tree.command(name="flip", description="Flip a coin")
async def flip(interaction: discord.Interaction):
    await interaction.response.defer()

    result = random.choice(["Heads", "Tails"])

    context = await get_recent_messages(interaction.channel, limit=20)
    prompt = f"I just flipped a coin for the user and it landed on {result}. Give them the result and add your own rude commentary about it."
    reaction = await call_ai(prompt, context)

    await interaction.followup.send(reaction)

@client.tree.command(name="roll", description="Roll some dice (e.g. 2d6)")
@app_commands.describe(dice="Format: NdN (like 2d6 or 1d20)")
async def roll(interaction: discord.Interaction, dice: str):
    await interaction.response.defer()

    match = re.match(r"(\d+)d(\d+)", dice.lower())
    if not match:
        await interaction.followup.send("Are you stupid? Use the NdN format, like 2d6 or 1d20.")
        return

    num_dice, num_sides = map(int, match.groups())

    if num_dice > 100 or num_sides > 1000:
        await interaction.followup.send("I'm not rolling that many dice or sides, you absolute lunatic. Keep it under 100d1000.")
        return

    if num_dice < 1 or num_sides < 1:
        await interaction.followup.send("You can't roll zero dice or zero sides. Think before you type.")
        return

    rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
    total = sum(rolls)

    roll_str = f"Rolled {dice}: {rolls} (Total: {total})"

    context = await get_recent_messages(interaction.channel, limit=20)
    prompt = f"The user rolled dice: {dice}. The result was {rolls} totaling {total}. Deliver this result to them with your signature attitude."
    reaction = await call_ai(prompt, context)

    await interaction.followup.send(reaction)

if __name__ == "__main__":
    if DISCORD_BOT_TOKEN:
        client.run(DISCORD_BOT_TOKEN)
    else:
        print("Please set DISCORD_BOT_TOKEN in .env")
