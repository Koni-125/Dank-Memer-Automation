import asyncio
import re

from discord.ext import commands

DANK_MEMER_ID = 270904126974590976

# Dank Memer blackjack is still legacy v1: a normal embed ("<name>'s
# Blackjack Game") plus ActionRow buttons with stable custom_ids:
#   blackjack-play:<user_id>:hit / stand / double / surrender
# There is NO split button, so pairs are played as their hard/soft total.
# Hand state lives in the embed fields:
#   "<Name> (Dealer)" -> cards + ` ? ` while the hole card is hidden
#   "<Name> (Player)" -> cards + ` <total> `
# Card faces are emojis like <:bjFace3B:...> / <:bjFace7R:...> /
# <:bjFaceUnknown:...> (hidden) / <:bjFaceAR:...> (ace). Rank part of the
# emoji name is the rank: number, A, J, Q, K. Trailing B/R is the color.
#
# Strategy: standard multi-deck basic strategy (dealer stands on soft 17,
# double-after-split assumed irrelevant without splits, late surrender).
# This is the mathematically optimal play under those standard rules;
# Dank Memer's exact table rules (S17 vs H17, BJ payout) are not published,
# but the chart is near-optimal for either common variant.

_FACE_RE = re.compile(r"bjFace([0-9]{1,2}|[AJQK])", re.IGNORECASE)
_TOTAL_RE = re.compile(r"`\s*(\d+)\s*`")
_SHOE_RE = re.compile(r"Shoe:\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)

_RANK_VALUE = {"A": 11, "K": 10, "Q": 10, "J": 10}

# Hi-Lo running-count values keyed by rank. 10 covers 10/J/Q/K.
_HI_LO = {
    "2": 1, "3": 1, "4": 1, "5": 1, "6": 1,
    "7": 0, "8": 0, "9": 0,
    "10": -1, "J": -1, "Q": -1, "K": -1, "A": -1,
}


def _face_value(face):
    face = face.upper()
    if face in _RANK_VALUE:
        return _RANK_VALUE[face]
    try:
        return int(face)
    except (TypeError, ValueError):
        return None


def _player_total(player_field_value):
    # Dank Memer's own displayed total (authoritative value).
    match = _TOTAL_RE.search(player_field_value or "")
    if not match:
        return None
    return int(match.group(1))


def _player_faces(player_field_value):
    return [m.group(1) for m in _FACE_RE.finditer(player_field_value or "")]


def _hand_value(faces):
    # Returns (total, soft). Soft = an ace is currently counted as 11.
    total = 0
    aces = 0
    for face in faces:
        value = _face_value(face)
        if value is None:
            continue
        if face.upper() == "A":
            aces += 1
        total += value
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, bool(aces)


def _dealer_upcard(dealer_field_value):
    # First visible (non-Unknown) face emoji is the upcard. Unknown hole
    # cards never match _FACE_RE, so they are skipped automatically.
    # Returns 2-11 where 11 means Ace.
    for match in _FACE_RE.finditer(dealer_field_value or ""):
        value = _face_value(match.group(1))
        if value is not None:
            return value
    return None


def _decide(total, soft, dealer_up, can_double, can_surrender):
    """Full basic-strategy decision: hit / stand / double / surrender.

    dealer_up is 2-11 (11 = Ace). can_double / can_surrender come from the
    live buttons (only enabled on the first decision with 2 cards).
    Fallbacks when the preferred move is unavailable: double -> hit
    (stand on soft 18), surrender -> normal hit/stand chart.
    """
    if total is None or total > 21:
        return None
    d = dealer_up
    ace = d == 11

    def double_or(action):
        return "double" if can_double else action

    # --- Late surrender (first decision only) ---
    if can_surrender and not soft and d is not None:
        if total == 16 and (d in (9, 10) or ace):
            return "surrender"
        if total == 15 and d == 10:
            return "surrender"

    # --- Soft totals ---
    if soft:
        if total <= 14:
            # A,A (=12) and A,2 / A,3.
            if total == 12:
                return "hit"
            if d in (5, 6):
                return double_or("hit")
            return "hit"
        if total in (15, 16):  # A,4 / A,5
            if d in (4, 5, 6):
                return double_or("hit")
            return "hit"
        if total == 17:  # A,6
            if d in (3, 4, 5, 6):
                return double_or("hit")
            return "hit"
        if total == 18:  # A,7
            if d in (3, 4, 5, 6):
                return double_or("stand")
            if d in (2, 7, 8):
                return "stand"
            return "hit"  # vs 9, 10, A
        return "stand"  # soft 19+

    # --- Hard totals ---
    if total <= 8:
        return "hit"
    if total == 9:
        if d in (3, 4, 5, 6):
            return double_or("hit")
        return "hit"
    if total == 10:
        if d is not None and 2 <= d <= 9:
            return double_or("hit")
        return "hit"
    if total == 11:
        if d is not None and 2 <= d <= 10:
            return double_or("hit")
        return "hit"  # vs Ace: hit (S17 game)
    if total == 12:
        if d in (4, 5, 6):
            return "stand"
        return "hit"
    if 13 <= total <= 16:
        if d is not None and 2 <= d <= 6:
            return "stand"
        return "hit"
    return "stand"  # hard 17+


def bet_for_count(true_count, base_bet):
    """Count-based bet ramp (units of base_bet). TC<=1: table minimum,
    TC 2: 2x, TC 3: 4x, TC>=4: 8x. No edge without spreading."""
    if true_count >= 4:
        return base_bet * 8
    if true_count == 3:
        return base_bet * 4
    if true_count == 2:
        return base_bet * 2
    return base_bet


class Blackjack(commands.Cog):
    """Normal-rotation blackjack player (legacy v1 embed + buttons)."""

    def __init__(self, bot):
        self.bot = bot
        self._last_action = None  # (message_id, total, decision)
        # Serializes _handle_message so the on_message + on_message_edit
        # listeners can't interleave on the same snapshot: check-guard and
        # click run atomically, so the game-over UPDATE racing the play
        # UPDATE can't slip past the guard and double-click.
        self._lock = asyncio.Lock()
        # Hi-Lo shoe state. _seen_hands holds (message_id, shoe_remaining)
        # keys for finished hands already tallied -- keyed this way (not
        # bare message id) so a future gamble-only mode that reuses one
        # message via Play Again still counts each hand exactly once.
        self.running_count = 0
        self._shoe_remaining = None
        self._seen_hands = set()

    @property
    def _counting_enabled(self):
        try:
            return bool(
                self.bot.settings_dict["commands"]["blackjack"].get(
                    "card_counting", False
                )
            )
        except (KeyError, TypeError, AttributeError):
            return False

    @property
    def _base_bet(self):
        try:
            return int(
                self.bot.settings_dict["commands"]["blackjack"].get(
                    "bet", 5000
                )
            )
        except (KeyError, TypeError, AttributeError, ValueError):
            return 5000

    def true_count(self):
        if self._shoe_remaining is None:
            return 0.0
        decks_left = max(self._shoe_remaining, 1) / 52.0
        return self.running_count / decks_left

    def current_bet(self):
        if not self._counting_enabled:
            return self._base_bet
        return bet_for_count(int(self.true_count() // 1), self._base_bet)

    def _tally_hand(self, message_id, player_value, dealer_value, shoe):
        """Tally one finished hand. Returns True if newly counted."""
        # Reshuffle: remaining jumps back up (fresh shoe first shows ~256,
        # not the full 260 -- so compare direction, not a fixed value).
        if (
            self._shoe_remaining is not None
            and shoe is not None
            and shoe > self._shoe_remaining
        ):
            self.running_count = 0
            self._seen_hands.clear()
        if shoe is not None:
            self._shoe_remaining = shoe
        key = (message_id, shoe)
        if key in self._seen_hands:
            return False
        self._seen_hands.add(key)
        delta = 0
        for face in _player_faces(player_value) + _player_faces(
            dealer_value
        ):
            delta += _HI_LO.get(face.upper(), 0)
        self.running_count += delta
        return True

    @commands.Cog.listener()
    async def on_message(self, message):
        await self._handle_message(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        await self._handle_message(after)

    async def _handle_message(self, message):
        async with self._lock:
            await self._handle_locked(message)

    async def _handle_locked(self, message):
        if message.channel.id != self.bot.channel.id:
            return
        if message.author.id != DANK_MEMER_ID:
            return
        if not message.embeds:
            return

        embed = message.embeds[0]
        author_name = (embed.author.name if embed.author else "") or ""
        # NOTE: blackjack uses the account *username* (kayote1234), not the
        # global/display name (highlow uses the global name). Accept both.
        names = {
            getattr(self.bot.user, "name", "") or "",
            getattr(self.bot.user, "global_name", "") or "",
        }
        if not any(
            n and f"{n}'s Blackjack Game" in author_name for n in names
        ):
            return

        fields = {f.name: (f.value or "") for f in (embed.fields or [])}
        player_value = next(
            (v for name, v in fields.items() if "(Player)" in name), None
        )
        dealer_value = next(
            (v for name, v in fields.items() if "(Dealer)" in name), None
        )
        if player_value is None:
            return

        # Value from our own card parse (gives soft/hard); cross-check
        # against Dank Memer's displayed total. If the faces don't parse
        # (mismatch), the hand is ambiguous -- and an A+7 shown as 18 is
        # exactly where soft-vs-hard matters (soft 18 hits vs 9/10/A,
        # hard 18 always stands). Fall back to soft on mismatch: hard
        # players stand on anything soft players would hit, the reverse
        # misplay (hitting hard 18) busts immediately.
        faces = _player_faces(player_value)
        shown = _player_total(player_value)
        if faces:
            computed, soft = _hand_value(faces)
            if shown is not None and computed != shown:
                total, soft = shown, True
            else:
                total = computed
        elif shown is not None:
            total, soft = shown, False
        else:
            return
        dealer_up = _dealer_upcard(dealer_value)

        # Footer shoe state: "Shoe: 237/260" (fresh shoe first shows ~256,
        # so reshuffle = remaining jumps back UP, never a fixed number).
        shoe = None
        footer = (embed.footer.text if embed.footer else "") or ""
        shoe_match = _SHOE_RE.search(footer)
        if shoe_match:
            shoe = int(shoe_match.group(1))

        # Only our own game's buttons (custom_id embeds our user id).
        # Game-over screens carry blackjack-again:/blackjack-start: ids;
        # mid-hand screens carry blackjack-play: ids.
        positions = {}
        game_over = False
        for ri, row in enumerate(list(getattr(message, "components", []) or [])):
            for ci, child in enumerate(getattr(row, "children", [])):
                cid = getattr(child, "custom_id", "") or ""
                if f"blackjack-play:{self.bot.user.id}" in cid:
                    for action in ("hit", "stand", "double", "surrender"):
                        if cid.endswith(f":{action}"):
                            positions[action] = (ri, ci, child)
                elif (
                    f"blackjack-again:{self.bot.user.id}" in cid
                    or f"blackjack-start:{self.bot.user.id}" in cid
                ):
                    game_over = True

        # Game-over: play buttons replaced by blackjack-again/start ids.
        # Require the game-over ids -- a transient button-less mid-hand
        # edit must NOT be tallied, or the real game-over tally dedupes
        # via _seen_hands and the full hand is never counted.
        if game_over:
            if self._counting_enabled and dealer_value is not None:
                if self._tally_hand(
                    message.id, player_value, dealer_value, shoe
                ):
                    self.bot.log(
                        f"blackjack - count RC={self.running_count} "
                        f"TC={self.true_count():+.2f} (shoe {shoe}) "
                        f"-> next bet {self.current_bet()}",
                        "blue",
                    )
            return

        can_double = (
            "double" in positions and not positions["double"][2].disabled
        )
        can_surrender = (
            "surrender" in positions and not positions["surrender"][2].disabled
        )
        decision = _decide(total, soft, dealer_up, can_double, can_surrender)
        if decision is None or decision not in positions:
            return

        key = (message.id, total, soft, decision)
        if key == self._last_action:
            return

        try:
            ri, ci, btn = positions[decision]
            if btn.disabled:
                return
            await self.bot.click(message, ri, ci)
            self._last_action = key
            hand = f"{'soft' if soft else 'hard'} {total}"
            self.bot.log(
                f"blackjack - {decision.capitalize()} on {hand} "
                f"(dealer {dealer_up})",
                "green",
            )
        except (IndexError, AttributeError) as e:
            self.bot.log(f"blackjack - click failed: {e}", "red")


async def setup(bot):
    await bot.add_cog(Blackjack(bot))
