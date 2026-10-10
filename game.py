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
