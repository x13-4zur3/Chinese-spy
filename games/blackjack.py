from __future__ import annotations

from dataclasses import dataclass, field

from games.deck import Card, Deck


def hand_value(cards: list[Card]) -> int:
    total = sum(card.blackjack_value for card in cards)
    aces = sum(1 for card in cards if card.rank == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def is_blackjack(cards: list[Card]) -> bool:
    return len(cards) == 2 and hand_value(cards) == 21


@dataclass
class BlackjackPlayerState:
    user_id: int
    display_name: str
    bet: int
    hand: list[Card] = field(default_factory=list)
    stood: bool = False
    busted: bool = False
    doubled: bool = False
    result: str | None = None
    payout: int = 0


@dataclass
class BlackjackTableGame:
    owner_id: int
    base_bet: int
    max_players: int = 2
    deck: Deck = field(default_factory=Deck)
    players: list[BlackjackPlayerState] = field(default_factory=list)
    dealer: list[Card] = field(default_factory=list)
    started: bool = False
    finished: bool = False
    turn_index: int = 0
    action_log: list[str] = field(default_factory=list)

    def add_player(self, user_id: int, display_name: str) -> bool:
        if self.started or self.finished:
            return False
        if len(self.players) >= self.max_players:
            return False
        if any(player.user_id == user_id for player in self.players):
            return False
        self.players.append(
            BlackjackPlayerState(user_id=user_id, display_name=display_name, bet=self.base_bet)
        )
        return True

    def has_user(self, user_id: int) -> bool:
        return any(player.user_id == user_id for player in self.players)

    def user_index(self, user_id: int) -> int | None:
        for idx, player in enumerate(self.players):
            if player.user_id == user_id:
                return idx
        return None

    def start_hand(self) -> None:
        if self.started:
            raise ValueError("A blackjack hand is already running.")
        if not self.players:
            raise ValueError("No players at this blackjack table.")

        self.deck = Deck()
        self.dealer = [self.deck.draw(), self.deck.draw()]
        self.started = True
        self.finished = False
        self.turn_index = 0
        self.action_log = []

        for player in self.players:
            player.hand = [self.deck.draw(), self.deck.draw()]
            player.stood = is_blackjack(player.hand)
            player.busted = False
            player.doubled = False
            player.result = None
            player.payout = 0

        self._sync_turn_index()
        if self._all_players_done():
            self._finalize()

    def _all_players_done(self) -> bool:
        return all(player.stood for player in self.players)

    def _sync_turn_index(self) -> None:
        if not self.players or self.finished:
            return
        if self._all_players_done():
            return
        if not self.players[self.turn_index].stood:
            return

        total = len(self.players)
        for offset in range(1, total + 1):
            idx = (self.turn_index + offset) % total
            if not self.players[idx].stood:
                self.turn_index = idx
                return

    def current_player(self) -> BlackjackPlayerState | None:
        if self.finished or not self.started or self._all_players_done():
            return None
        self._sync_turn_index()
        return self.players[self.turn_index]

    def _ensure_turn(self, user_id: int) -> BlackjackPlayerState:
        if not self.started or self.finished:
            raise ValueError("No active blackjack hand in progress.")
        player = self.current_player()
        if player is None:
            raise ValueError("No active blackjack turn right now.")
        if player.user_id != user_id:
            raise ValueError(f"It's {player.display_name}'s turn.")
        return player

    def can_double_for_user(self, user_id: int) -> bool:
        idx = self.user_index(user_id)
        if idx is None or self.finished or not self.started:
            return False
        if idx != self.turn_index:
            return False
        player = self.players[idx]
        return len(player.hand) == 2 and not player.doubled and not player.stood

    def hit(self, user_id: int) -> str:
        player = self._ensure_turn(user_id)
        player.hand.append(self.deck.draw())
        total = hand_value(player.hand)

        if total > 21:
            player.busted = True
            player.stood = True
            action_text = f"{player.display_name} hits and busts ({total})."
            self.action_log.append(action_text)
            self._advance_turn()
            return action_text

        action_text = f"{player.display_name} hits ({total})."
        self.action_log.append(action_text)
        return action_text

    def stand(self, user_id: int) -> str:
        player = self._ensure_turn(user_id)
        player.stood = True
        action_text = f"{player.display_name} stands on {hand_value(player.hand)}."
        self.action_log.append(action_text)
        self._advance_turn()
        return action_text

    def double(self, user_id: int) -> str:
        if not self.can_double_for_user(user_id):
            raise ValueError("You can only double on your first move of your turn.")

        player = self._ensure_turn(user_id)
        player.doubled = True
        player.bet *= 2
        player.hand.append(self.deck.draw())
        total = hand_value(player.hand)
        player.stood = True

        if total > 21:
            player.busted = True
            action_text = f"{player.display_name} doubles and busts ({total})."
        else:
            action_text = f"{player.display_name} doubles and stands on {total}."
        self.action_log.append(action_text)
        self._advance_turn()
        return action_text

    def _advance_turn(self) -> None:
        if self.finished:
            return
        if self._all_players_done():
            self._finalize()
            return

        total = len(self.players)
        for offset in range(1, total + 1):
            idx = (self.turn_index + offset) % total
            if not self.players[idx].stood:
                self.turn_index = idx
                return
        self._finalize()

    def _finalize(self) -> None:
        if self.finished:
            return

        if any(not player.busted for player in self.players):
            while hand_value(self.dealer) < 17:
                self.dealer.append(self.deck.draw())

        dealer_total = hand_value(self.dealer)
        dealer_bj = is_blackjack(self.dealer)

        for player in self.players:
            player_total = hand_value(player.hand)
            player_bj = is_blackjack(player.hand)

            if player_bj and dealer_bj:
                player.result = "push"
                player.payout = 0
            elif player_bj:
                player.result = "blackjack"
                player.payout = int(player.bet * 1.5)
            elif player.busted:
                player.result = "bust"
                player.payout = -player.bet
            elif dealer_bj:
                player.result = "dealer_blackjack"
                player.payout = -player.bet
            elif dealer_total > 21:
                player.result = "dealer_bust"
                player.payout = player.bet
            elif player_total > dealer_total:
                player.result = "win"
                player.payout = player.bet
            elif player_total < dealer_total:
                player.result = "lose"
                player.payout = -player.bet
            else:
                player.result = "push"
                player.payout = 0

        self.finished = True

    def public_dealer_cards(self, hide_hole: bool) -> list[str]:
        if not self.dealer:
            return []
        if hide_hole and not self.finished:
            return [str(self.dealer[0]), "🂠"]
        return [str(card) for card in self.dealer]
