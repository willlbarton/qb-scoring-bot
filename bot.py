import asyncio
import os
from pathlib import Path

import discord
from dotenv import load_dotenv

from game import Game, GameState


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
game = Game()
message_lock = asyncio.Lock()


@client.event
async def on_ready():
    print(f"Connected as {client.user}. Type !read in your Discord channel to start.")


@client.event
async def on_message(message: discord.Message):
    global game

    if message.author.bot or message.guild is None:
        return

    async with message_lock:
        content = message.content.strip().lower()

        if content == "!read":
            if game.game_state == GameState.STOPPED:
                game = Game()
                await game.handle_read(message)
            return

        if game.game_state == GameState.STOPPED:
            return
        
        if message.channel.id != game.game_channel.id:
            return

        if content == "buzz" or content == "bz":
            await game.handle_buzz(message)

        elif content in ("withdraw", "wd"):
            await game.handle_withdraw(message)
            
        elif content == "!next":
            if message.author.id == game.reader:
                await game.handle_next_tossup()

        elif content == "!end":
            await game.handle_end(message)

        else:
            await game.handle_score(message)


if __name__ == "__main__":
    load_dotenv(Path(__file__).with_name(".env"))
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token or token == "paste_your_bot_token_here":
        raise SystemExit("Paste your bot token into DISCORD_TOKEN in .env, then run again.")
    client.run(token)
