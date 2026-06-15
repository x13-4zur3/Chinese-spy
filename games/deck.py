from __future__ import annotations

import random
from dataclasses import dataclass


RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["♠", "♥", "♦", "♣"]


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    @property
    def blackjack_value(self) -> int:
        if self.rank in {"J", "Q", "K"}:
            return 10
        if self.rank == "A":
            return 11
        return int(self.rank)

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"


class Deck:
    def __init__(self, decks: int = 1) -> None:
        self.cards: list[Card] = [
            Card(rank, suit)
            for _ in range(decks)
            for suit in SUITS
            for rank in RANKS
        ]
        random.shuffle(self.cards)

    def draw(self) -> Card:
        if not self.cards:
            raise RuntimeError("Deck is empty")
        return self.cards.pop()

    def remaining(self) -> int:
        return len(self.cards)
