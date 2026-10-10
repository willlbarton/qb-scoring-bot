import discord
from enum import Enum, auto
from collections import deque

VALID_SCORES = [15, 10, -5, 0]

class GameState(Enum):
    READING = auto()
    WAITING = auto()
    STOPPED = auto()

class Game:
    def __init__(self):
        self.tossup_number = 0
        self.reader = None
        self.current_player = None
        self.already_buzzed = set()
        self.game_state = GameState.STOPPED
        self.buzz_queue = deque()
        self.game_channel = None
        self.scores_map = {}  # user_id: [#15s, #10s, #-5s, #0s]


    async def handle_read(self, message: discord.Message):
        if self.reader or self.game_state != GameState.STOPPED:
            return

        self.reader = message.author.id
        self.game_channel = message.channel
        self.tossup_number = 1

        await message.channel.send(f"{message.author.mention} is the reader.")
        self.game_state = GameState.READING

    async def handle_buzz(self, message: discord.Message):
        buzzer_id = message.author.id

        if buzzer_id == self.reader or buzzer_id in self.already_buzzed:
            return

        if self.game_state == GameState.READING:
            self.game_state = GameState.WAITING
            self.current_player = buzzer_id
            self.already_buzzed.add(buzzer_id)

            await message.channel.send(message.author.mention)

        elif self.game_state == GameState.WAITING:
            self.already_buzzed.add(buzzer_id)
            self.buzz_queue.append(buzzer_id)

    async def handle_incorrect_buzz(self):
        if not self.buzz_queue:
            self.current_player = None
            self.game_state = GameState.READING
            return

        self.current_player = self.buzz_queue.popleft()
        await self.game_channel.send(f"<@{self.current_player}>")

    async def handle_withdraw(self, message: discord.Message):
        if message.author.id != self.current_player:
            return

        self.current_player = None
        self.already_buzzed.remove(message.author.id)

        await message.channel.send(f"{message.author.mention} has withdrawn.")
        await self.handle_incorrect_buzz()

    async def handle_score(self, message: discord.Message):
        if message.author.id != self.reader:
            return

        try:
            score = int(message.content.strip())
        except ValueError:
            return

        if self.game_state != GameState.WAITING or self.current_player is None or score not in VALID_SCORES:
            return

        if self.current_player not in self.scores_map:
            self.scores_map[self.current_player] = [0] * 4

        self.scores_map[self.current_player][VALID_SCORES.index(score)] += 1

        if score > 0:
            await self.handle_next_tossup()
        else:
            await self.handle_incorrect_buzz()
    
    async def handle_next_tossup(self):
        self.tossup_number += 1
        self.buzz_queue.clear()
        self.already_buzzed.clear()
        self.current_player = None
        self.game_state = GameState.READING

        await self.game_channel.send(f"TU {self.tossup_number}")
