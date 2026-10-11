"""Offline tests: real handlers and embeds, fake Discord messages/channels."""
import asyncio
import unittest
from types import SimpleNamespace

import bot
from game import Game, GameState


class Channel:
    def __init__(self, channel_id=100):
        self.id = channel_id
        self.sent = []
        self.entered = None
        self.release = None

    async def send(self, content=None, **kwargs):
        self.sent.append((content, kwargs))
        if self.entered is not None:
            self.entered.set()
            await self.release.wait()


def message(text, user=1, channel=None, *, is_bot=False, guild=1, name=None):
    return SimpleNamespace(
        content=text,
        author=SimpleNamespace(id=user, mention=f"<@{user}>",
                               display_name=name or f"Player {user}", bot=is_bot),
        channel=channel, guild=guild,
    )


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        bot.game = Game()
        bot.message_lock = asyncio.Lock()
        self.channel = Channel()

    async def send(self, text, user=1, **kwargs):
        await bot.on_message(message(text, user, kwargs.pop("channel", self.channel), **kwargs))

    async def start(self):
        await self.send("!read")

    def texts(self):
        return [content for content, _ in self.channel.sent if content is not None]

    def embeds(self):
        return [kwargs["embed"] for _, kwargs in self.channel.sent if "embed" in kwargs]

    async def test_start_sets_reader_channel_state_and_bold_tossup(self):
        await self.start()
        self.assertEqual(bot.game.reader, 1)
        self.assertIs(bot.game.game_channel, self.channel)
        self.assertEqual(bot.game.tossup_number, 1)
        self.assertEqual(bot.game.game_state, GameState.READING)
        self.assertEqual(self.texts(), ["<@1> is the reader.", "**TU 1**"])

    async def test_commands_before_start_are_ignored(self):
        for text in ("buzz", "bz", "withdraw", "wd", "15", "!next", "!end", "hello"):
            await self.send(text, 2)
        self.assertEqual(self.channel.sent, [])
        self.assertEqual(bot.game.scores_map, {})

    async def test_bots_and_dms_cannot_start(self):
        await self.send("!read", is_bot=True)
        await self.send("!read", guild=None)
        self.assertEqual(bot.game.game_state, GameState.STOPPED)

    async def test_second_read_is_ignored_in_same_or_other_server(self):
        await self.start()
        original = bot.game
        await self.send("!read", 2)
        other = Channel(200)
        await self.send("!read", 2, channel=other, guild=2)
        self.assertIs(bot.game, original)
        self.assertEqual(bot.game.reader, 1)
        self.assertEqual(other.sent, [])

    async def test_other_channels_cannot_buzz_score_withdraw_skip_or_end(self):
        await self.start()
        await self.send("buzz", 2)
        other = Channel(200)
        for text, user in (("buzz", 3), ("15", 1), ("withdraw", 2), ("!next", 1), ("!end", 1)):
            await self.send(text, user, channel=other, guild=2)
        self.assertEqual(bot.game.current_player, 2)
        self.assertEqual(bot.game.tossup_number, 1)
        self.assertEqual(bot.game.scores_map, {2: [0, 0, 0, 0]})
        self.assertEqual(other.sent, [])

    async def test_reader_cannot_buzz_and_queue_is_fifo_without_duplicates(self):
        await self.start()
        await self.send("buzz", 1)
        for user in (2, 3, 4, 2, 3):
            await self.send("buzz", user)
        self.assertEqual(bot.game.current_player, 2)
        self.assertEqual(list(bot.game.buzz_queue), [3, 4])
        self.assertEqual(bot.game.already_buzzed, {2, 3, 4})
        self.assertEqual(self.texts()[-1], "<@2>")
        self.assertEqual(bot.game.scores_map[3], [0, 0, 0, 0])

    async def test_command_whitespace_case_and_aliases(self):
        await self.send("  !READ  ")
        await self.send(" BZ ", 2)
        await self.send(" WD ", 2)
        self.assertEqual(bot.game.game_state, GameState.READING)
        self.assertNotIn(2, bot.game.already_buzzed)

    async def test_all_valid_scores_record_in_correct_slots(self):
        for score, slot in ((15, 0), (10, 1), (-5, 2), (0, 3)):
            with self.subTest(score=score):
                bot.game = Game()
                await self.start()
                await self.send("buzz", 2)
                await self.send(str(score))
                expected = [0] * 4
                expected[slot] = 1
                self.assertEqual(bot.game.scores_map[2], expected)
                self.assertEqual(bot.game.tossup_number, 2 if score > 0 else 1)
                self.assertEqual(bot.game.game_state, GameState.READING)

    async def test_invalid_scores_and_nonreader_scores_are_ignored(self):
        await self.start()
        await self.send("buzz", 2)
        for text in ("", "hello", "5", "-10", "20", "10.0", "!unknown"):
            await self.send(text)
        for user in (2, 3):
            await self.send("15", user)
        self.assertEqual(bot.game.current_player, 2)
        self.assertEqual(bot.game.scores_map[2], [0] * 4)
        await self.send("  +10  ")
        self.assertEqual(bot.game.scores_map[2], [0, 1, 0, 0])

    async def test_scores_without_current_player_are_ignored(self):
        await self.start()
        await self.send("15")
        self.assertEqual(bot.game.tossup_number, 1)
        self.assertEqual(bot.game.scores_map, {})

    async def test_wrong_scores_advance_queue_then_resume_reading(self):
        await self.start()
        for user in (2, 3, 4):
            await self.send("buzz", user)
        await self.send("-5")
        self.assertEqual(bot.game.current_player, 3)
        await self.send("0")
        self.assertEqual(bot.game.current_player, 4)
        await self.send("-5")
        self.assertIsNone(bot.game.current_player)
        self.assertEqual(bot.game.game_state, GameState.READING)
        await self.send("buzz", 2)
        self.assertIsNone(bot.game.current_player)
        await self.send("buzz", 5)
        self.assertEqual(bot.game.current_player, 5)

    async def test_correct_scores_clear_queue_and_allow_rebuzz_next_tossup(self):
        await self.start()
        await self.send("buzz", 2)
        await self.send("buzz", 3)
        await self.send("15")
        self.assertFalse(bot.game.buzz_queue)
        self.assertFalse(bot.game.already_buzzed)
        self.assertIsNone(bot.game.current_player)
        self.assertEqual(self.texts()[-1], "**TU 2**")
        await self.send("buzz", 2)
        await self.send("10")
        self.assertEqual(bot.game.scores_map[2], [1, 1, 0, 0])

    async def test_only_current_player_can_withdraw(self):
        await self.start()
        await self.send("buzz", 2)
        await self.send("buzz", 3)
        before = len(self.channel.sent)
        for user in (1, 3, 4):
            await self.send("withdraw", user)
        self.assertEqual(len(self.channel.sent), before)
        self.assertEqual(bot.game.current_player, 2)
        self.assertEqual(list(bot.game.buzz_queue), [3])

    async def test_withdraw_announces_before_next_ping_and_allows_rebuzz(self):
        await self.start()
        await self.send("buzz", 2)
        await self.send("buzz", 3)
        await self.send("withdraw", 2)
        self.assertEqual(self.texts()[-2:], ["<@2> has withdrawn.", "<@3>"])
        self.assertEqual(bot.game.current_player, 3)
        self.assertEqual(bot.game.scores_map[2], [0] * 4)
        await self.send("buzz", 2)
        self.assertEqual(list(bot.game.buzz_queue), [2])

    async def test_withdraw_empty_queue_resumes_reading(self):
        await self.start()
        await self.send("buzz", 2)
        await self.send("withdraw", 2)
        self.assertIsNone(bot.game.current_player)
        self.assertEqual(bot.game.game_state, GameState.READING)
        await self.send("buzz", 2)
        self.assertEqual(bot.game.current_player, 2)

    async def test_next_reader_only_resets_buzzes_preserves_scores(self):
        await self.start()
        await self.send("buzz", 2)
        await self.send("-5")
        await self.send("buzz", 3)
        await self.send("!next", 2)
        self.assertEqual(bot.game.tossup_number, 1)
        await self.send("!next")
        self.assertEqual(bot.game.tossup_number, 2)
        self.assertFalse(bot.game.buzz_queue)
        self.assertFalse(bot.game.already_buzzed)
        self.assertIsNone(bot.game.current_player)
        self.assertEqual(bot.game.scores_map[2], [0, 0, 1, 0])

    async def test_end_reader_only_stops_and_new_read_starts_fresh(self):
        await self.start()
        await self.send("buzz", 2)
        await self.send("0")
        await self.send("!end", 2)
        self.assertEqual(bot.game.game_state, GameState.READING)
        await self.send("!end")
        self.assertEqual(bot.game.game_state, GameState.STOPPED)
        self.assertEqual(len(self.embeds()), 1)
        await self.send("buzz", 3)
        await self.send("15")
        await self.send("!end")
        self.assertEqual(len(self.embeds()), 1)
        await self.send("!read", 3)
        self.assertEqual(bot.game.reader, 3)
        self.assertEqual(bot.game.tossup_number, 1)
        self.assertEqual(bot.game.scores_map, {})

    async def test_scoreboard_ranking_totals_counts_medals_and_no_penalties(self):
        await self.start()
        bot.game.player_names = {2: "Alice", 3: "Bob", 4: "Charlie", 5: "Dana"}
        bot.game.scores_map = {5: [0, 0, 1, 0], 3: [9, 6, 0, 2],
                              2: [7, 10, 1, 1], 4: [0, 0, 0, 0]}
        await self.send("!end")
        embed = self.embeds()[0]
        self.assertEqual(embed.title, "Scores")
        self.assertEqual(embed.colour.value, 0xF1C40F)
        self.assertEqual(embed.description,
            "🥇 **Alice**\n**200** (7/10/1) (1 no penalty buzz)\n\n"
            "🥈 **Bob**\n**195** (9/6/0) (2 no penalty buzzes)\n\n"
            "🥉 **Charlie**\n**0** (0/0/0)\n\n**Dana**\n**-5** (0/0/1)")
        mentions = self.channel.sent[-1][1]["allowed_mentions"]
        self.assertFalse(mentions.users)
        self.assertFalse(mentions.everyone)

    async def test_empty_scoreboard_and_ties(self):
        await self.start()
        await bot.game.print_scores()
        self.assertEqual(self.embeds()[-1].description, "No players recorded.")
        bot.game.scores_map = {2: [2, 0, 0, 0], 3: [2, 1, 2, 0]}
        await bot.game.print_scores()
        description = self.embeds()[-1].description
        self.assertLess(description.index("**2**"), description.index("**3**"))
        self.assertEqual(description.count("**30**"), 2)

    async def test_long_scoreboard_splits_without_losing_players(self):
        await self.start()
        bot.game.scores_map = {user: [0, 0, 0, 0] for user in range(1000, 1200)}
        bot.game.player_names = {user: f"Name {user}" for user in bot.game.scores_map}
        await bot.game.print_scores()
        embeds = self.embeds()
        self.assertGreater(len(embeds), 1)
        combined = "\n".join(embed.description for embed in embeds)
        for embed in embeds:
            self.assertLessEqual(len(embed.description), 4096)
        for user in bot.game.scores_map:
            self.assertEqual(combined.count(f"**Name {user}**"), 1)

    async def test_display_names_escape_markdown(self):
        await self.start()
        await self.send("buzz", 2, name="A *bold* name")
        await self.send("!end")
        self.assertIn(r"A \*bold\* name", self.embeds()[0].description)

    async def test_concurrent_buzzes_get_one_current_player_and_fifo_queue(self):
        await self.start()
        self.channel.entered = asyncio.Event()
        self.channel.release = asyncio.Event()
        first = asyncio.create_task(self.send("buzz", 2))
        await asyncio.wait_for(self.channel.entered.wait(), 1)
        second = asyncio.create_task(self.send("buzz", 3))
        await asyncio.sleep(0)
        self.assertEqual(bot.game.current_player, 2)
        self.assertFalse(bot.game.buzz_queue)
        self.channel.release.set()
        await asyncio.gather(first, second)
        self.assertEqual(list(bot.game.buzz_queue), [3])

    async def test_buzz_during_withdraw_send_waits_then_rebuzz_is_accepted(self):
        await self.start()
        await self.send("buzz", 2)
        await self.send("buzz", 3)
        self.channel.entered = asyncio.Event()
        self.channel.release = asyncio.Event()
        withdrawal = asyncio.create_task(self.send("withdraw", 2))
        await asyncio.wait_for(self.channel.entered.wait(), 1)
        rebuzz = asyncio.create_task(self.send("buzz", 2))
        await asyncio.sleep(0)
        self.assertFalse(rebuzz.done())
        self.channel.release.set()
        await asyncio.gather(withdrawal, rebuzz)
        self.assertEqual(bot.game.current_player, 3)
        self.assertEqual(list(bot.game.buzz_queue), [2])


if __name__ == "__main__":
    unittest.main()
