import discord
from enum import Enum, auto
from collections import deque

class GameState(Enum):
    READING = auto()
    WAITING = auto()
    STOPPED = auto()

tossup_number = 0
reader = None
current_player = None
already_buzzed = set()
game_state = GameState.STOPPED
buzz_queue = deque()
game_channel = None

async def handle_buzz(message: discord.Message):
    global reader, current_player, game_state
    buzzer_id = message.author.id

    if buzzer_id == reader or buzzer_id in already_buzzed:
        return
    
    if game_state == GameState.READING:
        game_state = GameState.WAITING
        current_player = buzzer_id
        already_buzzed.add(buzzer_id)

        await message.channel.send(message.author.mention)

    elif game_state == GameState.WAITING:
        already_buzzed.add(buzzer_id)
        buzz_queue.append(buzzer_id)

async def handle_incorrect_buzz():
    global buzz_queue, game_state, current_player, game_channel

    if not buzz_queue:
        current_player = None
        game_state = GameState.READING
        return

    current_player = buzz_queue.popleft()
    await game_channel.send(f"<@{current_player}>")

async def handle_withdraw(message: discord.Message):
    global current_player

    if message.author.id != current_player:
        return

    current_player = None
    already_buzzed.remove(message.author.id)
    
    await message.channel.send(f"{message.author.mention} has withdrawn.")
    await handle_incorrect_buzz()
