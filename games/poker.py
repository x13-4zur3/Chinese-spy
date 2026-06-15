from __future__ import annotations

import random
from dataclasses import dataclass, field

from treys import Card as TreysCard
from treys import Deck as TreysDeck
from treys import Evaluator


HAND_TYPE_MAP = {
    1: "Straight Flush",
    2: "Four of a Kind",
    3: "Full House",
    4: "Flush",
    5: "Straight",
    6: "Three of a Kind",
    7: "Two Pair",
    8: "One Pair",
    9: "High Card",
}


def pretty_card(card_int: int) -> str:
    text = TreysCard.int_to_str(card_int)
    suit_map = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
    return f"{text[0]}{suit_map.get(text[1], text[1])}"


@dataclass
class PokerSeat:
    user_id: int | None
    display_name: str
    is_bot: bool = False
    hole_cards: list[int] = field(default_factory=list)
    folded: bool = False


@dataclass
class PokerTableGame:
    minimum_bet: int
    owner_id: int
    max_players: int = 8
    deck: TreysDeck = field(default_factory=TreysDeck)
    evaluator: Evaluator = field(default_factory=Evaluator)
    seats: list[PokerSeat] = field(default_factory=list)
    board: list[int] = field(default_factory=list)
    stage: str = "lobby"
    started: bool = False
    finished: bool = False
    pot: int = 0
    current_bet: int = 0
    turn_index: int = 0
    round_commitments: dict[int, int] = field(default_factory=dict)
    total_commitments: dict[int, int] = field(default_factory=dict)
    acted_this_round: set[int] = field(default_factory=set)
    winner_indexes: list[int] = field(default_factory=list)
    hand_classes: dict[int, int] = field(default_factory=dict)
    last_action: str = ""
    action_history: list[str] = field(default_factory=list)

    def add_human(self, user_id: int, display_name: str) -> bool:
        if self.started or self.finished:
            return False
        if len(self.seats) >= self.max_players:
            return False
        if any(seat.user_id == user_id for seat in self.seats if not seat.is_bot):
            return False
        self.seats.append(PokerSeat(user_id=user_id, display_name=display_name))
        return True

    def add_bot(self) -> bool:
        if self.started or self.finished:
            return False
        if any(seat.is_bot for seat in self.seats):
            return False
        self.seats.append(PokerSeat(user_id=None, display_name="House Bot", is_bot=True))
        return True

    def has_user(self, user_id: int) -> bool:
        return any(seat.user_id == user_id for seat in self.seats if not seat.is_bot)

    def user_index(self, user_id: int) -> int | None:
        for idx, seat in enumerate(self.seats):
            if seat.user_id == user_id and not seat.is_bot:
                return idx
        return None

    def human_count(self) -> int:
        return sum(1 for seat in self.seats if not seat.is_bot)

    def active_indexes(self) -> list[int]:
        return [idx for idx, seat in enumerate(self.seats) if not seat.folded]

    def first_active_index(self) -> int | None:
        for idx in range(len(self.seats)):
            if not self.seats[idx].folded:
                return idx
        return None

    def next_active_index(self, current_index: int) -> int:
        if not self.seats:
            raise ValueError("No poker seats are available.")
        total = len(self.seats)
        for offset in range(1, total + 1):
            idx = (current_index + offset) % total
            if not self.seats[idx].folded:
                return idx
        return current_index

    def start_hand(self) -> None:
        if self.started:
            raise ValueError("A poker hand is already running.")
        if len(self.seats) < 2:
            raise ValueError("At least two players are required.")

        self.deck = TreysDeck()
        self.board = []
        self.stage = "preflop"
        self.started = True
        self.finished = False
        self.pot = 0
        self.current_bet = 0
        self.round_commitments = {}
        self.total_commitments = {}
        self.acted_this_round = set()
        self.winner_indexes = []
        self.hand_classes = {}
        self.last_action = ""
        self.action_history = []

        for idx, seat in enumerate(self.seats):
            seat.hole_cards = self.deck.draw(2)
            seat.folded = False
            self.round_commitments[idx] = 0
            self.total_commitments[idx] = 0

        first = self.first_active_index()
        if first is None:
            raise ValueError("No active players available to start poker.")
        self.turn_index = first

    def to_call_for_index(self, index: int) -> int:
        return max(0, self.current_bet - self.round_commitments.get(index, 0))

    def required_chips_for_index(self, index: int, action: str, amount: int = 0) -> int:
        if not self.started or self.finished:
            raise ValueError("No active poker hand in progress.")
        if index != self.turn_index:
            raise ValueError("It's not your turn.")

        seat = self.seats[index]
        if seat.folded:
            raise ValueError("You already folded this hand.")

        normalized = action.lower().strip()
        to_call = self.to_call_for_index(index)

        if normalized == "fold":
            return 0
        if normalized == "check":
            if to_call > 0:
                raise ValueError(f"You must call {to_call:,}, raise, or fold.")
            return 0
        if normalized == "call":
            return to_call
        if normalized == "bet":
            if self.current_bet != 0:
                raise ValueError("A bet already exists. Use raise, call, or fold.")
            if amount < self.minimum_bet:
                raise ValueError(f"Minimum bet is {self.minimum_bet:,}.")
            return amount
        if normalized == "raise":
            if self.current_bet == 0:
                raise ValueError("No active bet to raise. Use bet instead.")
            if amount < self.minimum_bet:
                raise ValueError(f"Minimum raise amount is {self.minimum_bet:,}.")
            return to_call + amount

        raise ValueError("Action must be check, call, bet, raise, or fold.")

    def required_human_chips(self, user_id: int, action: str, amount: int = 0) -> int:
        index = self.user_index(user_id)
        if index is None:
            raise ValueError("You are not seated at this table.")
        return self.required_chips_for_index(index, action, amount)

    def apply_human_action(
        self, user_id: int, action: str, amount: int = 0, committed: int | None = None
    ) -> str:
        index = self.user_index(user_id)
        if index is None:
            raise ValueError("You are not seated at this table.")
        return self.apply_action_by_index(index, action, amount, committed)

    def apply_action_by_index(
        self,
        index: int,
        action: str,
        amount: int = 0,
        committed: int | None = None,
    ) -> str:
        required = self.required_chips_for_index(index, action, amount)
        paid = required if committed is None else committed
        if paid != required:
            raise ValueError("Committed chip amount does not match required action cost.")

        seat = self.seats[index]
        normalized = action.lower().strip()

        if normalized == "fold":
            seat.folded = True
            self.acted_this_round.add(index)
            action_text = f"{seat.display_name} folds."
        else:
            if paid > 0:
                self.round_commitments[index] = self.round_commitments.get(index, 0) + paid
                self.total_commitments[index] = self.total_commitments.get(index, 0) + paid
                self.pot += paid

            if normalized == "check":
                self.acted_this_round.add(index)
                action_text = f"{seat.display_name} checks."
            elif normalized == "call":
                self.acted_this_round.add(index)
                if paid > 0:
                    action_text = f"{seat.display_name} calls {paid:,}."
                else:
                    action_text = f"{seat.display_name} checks."
            elif normalized == "bet":
                self.current_bet = self.round_commitments[index]
                self.acted_this_round = {index}
                action_text = f"{seat.display_name} bets {paid:,}."
            elif normalized == "raise":
                self.current_bet = self.round_commitments[index]
                self.acted_this_round = {index}
                action_text = f"{seat.display_name} raises by {amount:,} (total {paid:,})."
            else:
                raise ValueError("Unsupported poker action.")

        self.last_action = action_text
        self.action_history.append(action_text)
        if len(self.action_history) > 8:
            self.action_history = self.action_history[-8:]

        remaining = self.active_indexes()
        if len(remaining) == 1:
            self.finished = True
            self.stage = "finished"
            self.winner_indexes = [remaining[0]]
            return action_text

        if self._betting_round_complete():
            self._advance_round()
        else:
            self.turn_index = self.next_active_index(index)

        return action_text

    def _betting_round_complete(self) -> bool:
        active = self.active_indexes()
        if len(active) <= 1:
            return True
        for idx in active:
            if idx not in self.acted_this_round:
                return False
            if self.round_commitments.get(idx, 0) != self.current_bet:
                return False
        return True

    def _reset_round(self) -> None:
        self.current_bet = 0
        self.acted_this_round = set()
        for idx in range(len(self.seats)):
            if not self.seats[idx].folded:
                self.round_commitments[idx] = 0
        first = self.first_active_index()
        if first is not None:
            self.turn_index = first

    def _advance_round(self) -> None:
        if self.stage == "preflop":
            self.board.extend(self.deck.draw(3))
            self.stage = "flop"
            self._reset_round()
            return
        if self.stage == "flop":
            self.board.extend(self.deck.draw(1))
            self.stage = "turn"
            self._reset_round()
            return
        if self.stage == "turn":
            self.board.extend(self.deck.draw(1))
            self.stage = "river"
            self._reset_round()
            return
        if self.stage == "river":
            self._resolve_showdown()

    def _resolve_showdown(self) -> None:
        active = self.active_indexes()
        if not active:
            self.finished = True
            self.stage = "finished"
            self.winner_indexes = []
            return

        scores: dict[int, int] = {}
        for idx in active:
            score = self.evaluator.evaluate(self.board, self.seats[idx].hole_cards)
            scores[idx] = score
            self.hand_classes[idx] = self.evaluator.get_rank_class(score)

        best_score = min(scores.values())
        self.winner_indexes = sorted(
            idx for idx, score in scores.items() if score == best_score
        )
        self.finished = True
        self.stage = "finished"

    def payouts_by_index(self) -> dict[int, int]:
        if not self.finished or not self.winner_indexes:
            return {}
        winners = sorted(self.winner_indexes)
        share = self.pot // len(winners)
        remainder = self.pot % len(winners)
        payouts: dict[int, int] = {}
        for offset, idx in enumerate(winners):
            payouts[idx] = share + (1 if offset < remainder else 0)
        return payouts

    def net_by_index(self, index: int) -> int:
        payout = self.payouts_by_index().get(index, 0)
        invested = self.total_commitments.get(index, 0)
        return payout - invested

    def board_text(self) -> str:
        if not self.board:
            return "No community cards yet."
        return " ".join(pretty_card(card) for card in self.board)

    def stage_label(self) -> str:
        labels = {
            "lobby": "Lobby",
            "preflop": "Pre-flop",
            "flop": "Flop",
            "turn": "Turn",
            "river": "River",
            "finished": "Showdown",
        }
        return labels.get(self.stage, self.stage.title())

    def current_actor(self) -> PokerSeat | None:
        if self.finished or not self.started or not self.seats:
            return None
        return self.seats[self.turn_index]

    def should_take_bot_turn(self) -> bool:
        actor = self.current_actor()
        return actor is not None and actor.is_bot

    def bot_turn_decision(self) -> tuple[str, int]:
        actor = self.current_actor()
        if actor is None or not actor.is_bot:
            raise ValueError("It is not the bot's turn.")
        index = self.turn_index
        to_call = self.to_call_for_index(index)
        strength = self._bot_strength(index)

        if to_call > 0:
            if to_call > self.minimum_bet * 4 and strength < 7:
                return "fold", 0
            if strength >= 8 and random.random() < 0.35:
                return "raise", self.minimum_bet
            if strength >= 5 or to_call <= self.minimum_bet:
                return "call", 0
            return "fold", 0

        if strength >= 8 and random.random() < 0.55:
            return "bet", self.minimum_bet * 2
        if strength >= 6 and random.random() < 0.40:
            return "bet", self.minimum_bet
        return "check", 0

    def _bot_strength(self, index: int) -> int:
        if len(self.board) >= 3:
            score = self.evaluator.evaluate(self.board, self.seats[index].hole_cards)
            rank_class = self.evaluator.get_rank_class(score)
            return max(1, 11 - rank_class)

        rank_map = {
            "2": 2,
            "3": 3,
            "4": 4,
            "5": 5,
            "6": 6,
            "7": 7,
            "8": 8,
            "9": 9,
            "T": 10,
            "J": 11,
            "Q": 12,
            "K": 13,
            "A": 14,
        }
        cards = self.seats[index].hole_cards
        card_a = TreysCard.int_to_str(cards[0])
        card_b = TreysCard.int_to_str(cards[1])
        rank_a = rank_map.get(card_a[0], 2)
        rank_b = rank_map.get(card_b[0], 2)
        suited = card_a[1] == card_b[1]
        pair = rank_a == rank_b

        score = rank_a + rank_b
        if suited:
            score += 2
        if pair:
            score += 10
        if max(rank_a, rank_b) >= 11:
            score += 2

        return max(1, min(10, score // 3))
