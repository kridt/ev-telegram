"""Bet tracking system for forward testing."""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BetStatus(str, Enum):
    """Status of a tracked bet."""
    PENDING = "pending"      # Match not started
    LIVE = "live"           # Match in progress
    WON = "won"             # Bet won
    LOST = "lost"           # Bet lost
    VOID = "void"           # Bet voided (postponed, etc.)
    PUSH = "push"           # Push/refund (exact line hit)


class TrackedBet(BaseModel):
    """A tracked bet with full details."""
    id: str = ""

    # Fixture info
    fixture_id: str
    fixture_name: str
    league: str
    kickoff: datetime

    # Bet details
    market: str
    selection: str
    line: Optional[float] = None

    # Odds at time of identification
    best_odds: float
    best_book: str
    fair_odds: float
    edge_percent: float
    all_odds: Dict[str, float] = Field(default_factory=dict)

    # Tracking
    status: BetStatus = BetStatus.PENDING
    stake: float = 10.0  # Default stake for simulation
    result: Optional[float] = None  # Actual result value (e.g., player shots)
    profit: Optional[float] = None
    settled_at: Optional[datetime] = None

    # Metadata
    logged_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def settle(self, result_value: float) -> None:
        """Settle the bet based on result."""
        self.result = result_value
        self.settled_at = datetime.now(timezone.utc)

        # Determine win/loss based on selection
        if "Over" in self.selection:
            threshold = self.line or 0.5
            if result_value > threshold:
                self.status = BetStatus.WON
                self.profit = self.stake * (self.best_odds - 1)
            elif result_value == threshold:
                self.status = BetStatus.PUSH
                self.profit = 0
            else:
                self.status = BetStatus.LOST
                self.profit = -self.stake
        elif "Under" in self.selection:
            threshold = self.line or 0.5
            if result_value < threshold:
                self.status = BetStatus.WON
                self.profit = self.stake * (self.best_odds - 1)
            elif result_value == threshold:
                self.status = BetStatus.PUSH
                self.profit = 0
            else:
                self.status = BetStatus.LOST
                self.profit = -self.stake
        else:
            # For non-over/under markets, need custom logic
            self.status = BetStatus.VOID
            self.profit = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "fixture_id": self.fixture_id,
            "fixture_name": self.fixture_name,
            "league": self.league,
            "kickoff": self.kickoff.isoformat(),
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "best_odds": self.best_odds,
            "best_book": self.best_book,
            "fair_odds": self.fair_odds,
            "edge_percent": self.edge_percent,
            "all_odds": self.all_odds,
            "status": self.status.value,
            "stake": self.stake,
            "result": self.result,
            "profit": self.profit,
            "settled_at": self.settled_at.isoformat() if self.settled_at else None,
            "logged_at": self.logged_at.isoformat(),
        }


class BetTracker:
    """Tracks value bets for forward testing."""

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize tracker with storage directory."""
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path("data/tracking")

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.bets_file = self.data_dir / "tracked_bets.json"
        self.bets: Dict[str, TrackedBet] = {}
        self._load_bets()

    def _load_bets(self) -> None:
        """Load bets from file."""
        if self.bets_file.exists():
            try:
                with open(self.bets_file, "r") as f:
                    data = json.load(f)
                for bet_data in data:
                    bet = TrackedBet(**{
                        **bet_data,
                        "kickoff": datetime.fromisoformat(bet_data["kickoff"]),
                        "logged_at": datetime.fromisoformat(bet_data["logged_at"]),
                        "settled_at": datetime.fromisoformat(bet_data["settled_at"]) if bet_data.get("settled_at") else None,
                        "status": BetStatus(bet_data["status"]),
                    })
                    self.bets[bet.id] = bet
                logger.info(f"Loaded {len(self.bets)} tracked bets")
            except Exception as e:
                logger.error(f"Error loading bets: {e}")

    def _save_bets(self) -> None:
        """Save bets to file."""
        try:
            data = [bet.to_dict() for bet in self.bets.values()]
            with open(self.bets_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving bets: {e}")

    def _generate_id(self, bet: TrackedBet) -> str:
        """Generate unique bet ID."""
        return f"{bet.fixture_id}_{bet.market}_{bet.selection}_{bet.best_book}".replace(" ", "_")

    def log_bet(self, value_bet: Any, stake: float = 10.0) -> Optional[TrackedBet]:
        """Log a new value bet for tracking."""
        try:
            # Create tracked bet from value bet
            tracked = TrackedBet(
                fixture_id=value_bet.fixture_id,
                fixture_name=value_bet.fixture_name,
                league=value_bet.league,
                kickoff=value_bet.kickoff if isinstance(value_bet.kickoff, datetime) else datetime.fromisoformat(str(value_bet.kickoff).replace("Z", "+00:00")),
                market=value_bet.market,
                selection=value_bet.selection,
                line=value_bet.line,
                best_odds=value_bet.best_odds,
                best_book=value_bet.best_book,
                fair_odds=value_bet.fair_odds,
                edge_percent=value_bet.edge_percent,
                all_odds=value_bet.all_odds,
                stake=stake,
            )

            # Generate ID
            tracked.id = self._generate_id(tracked)

            # Skip if already tracked
            if tracked.id in self.bets:
                return None

            # Add and save
            self.bets[tracked.id] = tracked
            self._save_bets()
            logger.info(f"Logged bet: {tracked.selection} @ {tracked.best_odds} ({tracked.edge_percent:.1f}% edge)")

            return tracked

        except Exception as e:
            logger.error(f"Error logging bet: {e}")
            return None

    def log_multiple(self, value_bets: List[Any], stake: float = 10.0, max_bets: int = 50) -> int:
        """Log multiple value bets. Returns count of new bets logged."""
        logged = 0
        for bet in value_bets[:max_bets]:
            if self.log_bet(bet, stake):
                logged += 1
        return logged

    def get_pending_bets(self) -> List[TrackedBet]:
        """Get all pending bets."""
        return [b for b in self.bets.values() if b.status == BetStatus.PENDING]

    def get_bets_for_fixture(self, fixture_id: str) -> List[TrackedBet]:
        """Get all bets for a fixture."""
        return [b for b in self.bets.values() if b.fixture_id == fixture_id]

    def settle_bet(self, bet_id: str, result_value: float) -> Optional[TrackedBet]:
        """Settle a bet with the result."""
        if bet_id not in self.bets:
            return None

        bet = self.bets[bet_id]
        bet.settle(result_value)
        self._save_bets()

        logger.info(f"Settled bet: {bet.selection} - Result: {result_value}, Status: {bet.status.value}, P&L: {bet.profit:.2f}")
        return bet

    def get_stats(self) -> Dict[str, Any]:
        """Get tracking statistics."""
        all_bets = list(self.bets.values())
        settled = [b for b in all_bets if b.status in [BetStatus.WON, BetStatus.LOST, BetStatus.PUSH]]
        won = [b for b in settled if b.status == BetStatus.WON]
        lost = [b for b in settled if b.status == BetStatus.LOST]

        total_profit = sum(b.profit or 0 for b in settled)
        total_staked = sum(b.stake for b in settled)

        return {
            "total_bets": len(all_bets),
            "pending": len([b for b in all_bets if b.status == BetStatus.PENDING]),
            "settled": len(settled),
            "won": len(won),
            "lost": len(lost),
            "pushed": len([b for b in settled if b.status == BetStatus.PUSH]),
            "win_rate": len(won) / len(settled) * 100 if settled else 0,
            "total_profit": total_profit,
            "total_staked": total_staked,
            "roi": total_profit / total_staked * 100 if total_staked > 0 else 0,
            "avg_odds_won": sum(b.best_odds for b in won) / len(won) if won else 0,
            "avg_edge": sum(b.edge_percent for b in all_bets) / len(all_bets) if all_bets else 0,
        }

    def get_recent_bets(self, limit: int = 20) -> List[TrackedBet]:
        """Get most recent bets."""
        sorted_bets = sorted(self.bets.values(), key=lambda b: b.logged_at, reverse=True)
        return sorted_bets[:limit]
