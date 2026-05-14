import asyncio
from datetime import date
from typing import Any, Optional

from app.services.mlb_api import MLBStatsAPI
from app.services.baseball_savant import BaseballSavantService
from app.services.pitcher_stats import PitcherStatsService
from app.services.weather import WeatherService
from app.services.umpire import UmpireService
from app.services.bullpen import BullpenService
from app.services.team_fatigue import TeamFatigueService
from app.services.team_offense import TeamOffenseService
from app.services.line_movement import LineMovementService
from app.services.platoon_splits import PlatoonSplitsService
from app.services.dog_score import DogScoreEngine
from app.services.correlation_engine import CorrelationEngine
from app.services.scoring_engine import ScoringEngine
from app.services.edge_engine import EdgeEngine
from app.services.score_lock import ScoreLockCache
from app.services.live_adjuster import LiveScoreAdjuster
from app.services.ai_picks import AIPicksEngine


async def _empty() -> dict:
    return {}


class DataCollector:

    def __init__(self):
        self.mlb = MLBStatsAPI()
        self.savant = BaseballSavantService()
        self.pitchers = PitcherStatsService()
        self.weather = WeatherService()
        self.umpire_svc = UmpireService()
        self.bullpen_svc = BullpenService()
        self.fatigue_svc = TeamFatigueService()
        self.offense_svc = TeamOffenseService()
        self.line_svc = LineMovementService()
        self.platoon_svc = PlatoonSplitsService()
        self.dog_engine = DogScoreEngine()
        self.correlation = CorrelationEngine()
        self.scorer = ScoringEngine()
        self.edge = EdgeEngine()
        self.lock = ScoreLockCache()
        self.live_adj = LiveScoreAdjuster()
        self.ai = AIPicksEngine()

    async def collect_and_score_slate(self, game_date: Optional[date] = None) -> list[dict[str, Any]]:
        games = await self.mlb.get_schedule(game_date)
        current_lines = await self.line_svc.get_current_totals()
        results = await asyncio.gather(*[self._score_game(g, current_lines) for g in games])
        order = {"Preview": 0, "Live": 1, "Final": 2}
        return sorted(
            results,
            key=lambda x: (order.get(x.get("abstract_state", "Preview"), 0), -x.get("total_score", 0)),
        )

    async def collect_with_ai(self, game_date: Optional[date] = None) -> dict[str, Any]:
        """Slate + AI picks payload — used by the AI tab."""
        games = await self.collect_and_score_slate(game_date)
        ai = self.ai.analyze_slate(games)
        return {"games": games, "ai_picks": ai}

    async def _score_game(self, game: dict[str, Any], current_lines: list) -> dict[str, Any]:
        venue_id = game.get("venue_id")
        away_pitcher_id = game.get("away_pitcher_id")
        home_pitcher_id = game.get("home_pitcher_id")
        away_pitcher_name = game.get("away_pitcher_name")
        home_pitcher_name = game.get("home_pitcher_name")
        away_team_id = game.get("away_team_id")
        home_team_id = game.get("home_team_id")
        game_pk = game.get("game_pk")
        series_game = game.get("series_game_number", 1)

        # Gather 1: all independent I/O in parallel
        (
            park_data,
            away_pitcher,
            home_pitcher,
            weather_data,
            away_bullpen_raw,
            home_bullpen_raw,
            away_fatigue,
            home_fatigue,
            away_offense,
            home_offense,
            away_recent_form,
            home_recent_form,
        ) = await asyncio.gather(
            self.savant.get_park_factor(venue_id),
            self.pitchers.get_pitcher_score(away_pitcher_id, away_pitcher_name),
            self.pitchers.get_pitcher_score(home_pitcher_id, home_pitcher_name),
            self.weather.get_game_weather(venue_id),
            self.mlb.get_bullpen_usage(away_team_id) if away_team_id else _empty(),
            self.mlb.get_bullpen_usage(home_team_id) if home_team_id else _empty(),
            self.fatigue_svc.get_fatigue(away_team_id, game_date=None) if away_team_id else _empty(),
            self.fatigue_svc.get_fatigue(home_team_id, game_date=None) if home_team_id else _empty(),
            self.offense_svc.get_team_offense(away_team_id),
            self.offense_svc.get_team_offense(home_team_id),
            self.pitchers.get_pitcher_recent_form(away_pitcher_id),
            self.pitchers.get_pitcher_recent_form(home_pitcher_id),
        )

        # Gather 2: platoon splits need pitcher scores from gather 1
        away_platoon, home_platoon = await asyncio.gather(
            self.platoon_svc.get_pitcher_matchup_score(
                away_pitcher_id, home_team_id, away_pitcher.get("under_score", 5.0)
            ) if away_pitcher_id and home_team_id else _empty(),
            self.platoon_svc.get_pitcher_matchup_score(
                home_pitcher_id, away_team_id, home_pitcher.get("under_score", 5.0)
            ) if home_pitcher_id and away_team_id else _empty(),
        )

        # Umpire
        hp_umpire = game.get("hp_umpire")
        if not hp_umpire:
            hp_umpire = await self.mlb.get_umpire_for_game(game_pk)
        umpire_name = (hp_umpire or {}).get("name")
        umpire_data = await self.umpire_svc.get_umpire_score(umpire_name)

        away_bullpen = self.bullpen_svc.score_bullpen_fatigue(away_bullpen_raw)
        home_bullpen = self.bullpen_svc.score_bullpen_fatigue(home_bullpen_raw)

        # Apply platoon + recent form adjustments to pitcher under_scores
        away_pitcher_score = _apply_pitcher_adjustments(
            away_pitcher, away_platoon, away_recent_form
        )
        home_pitcher_score = _apply_pitcher_adjustments(
            home_pitcher, home_platoon, home_recent_form
        )

        # Line movement + real moneyline odds
        away_team_name = game.get("away_team", "")
        home_team_name = game.get("home_team", "")
        game_state = game.get("abstract_state", "Preview")
        line_movement = self.line_svc.parse_movement(
            current_lines, away_team_name, home_team_name, game_state
        )
        moneyline = self.line_svc.extract_moneyline(
            current_lines, away_team_name, home_team_name, game_state
        )

        fatigue_under_avg = (
            away_fatigue.get("under_score", 5.0) + home_fatigue.get("under_score", 5.0)
        ) / 2.0

        scored = self.scorer.score_game(
            park_factor_data=park_data,
            away_pitcher_data=away_pitcher_score,
            home_pitcher_data=home_pitcher_score,
            weather_data=weather_data,
            umpire_data=umpire_data,
            away_bullpen_data=away_bullpen,
            home_bullpen_data=home_bullpen,
            away_offense_data=away_offense,
            home_offense_data=home_offense,
            line_movement_data=line_movement,
            fatigue_score=fatigue_under_avg,
        )

        dog_data = self.dog_engine.score(
            game=game,
            away_fatigue=away_fatigue,
            home_fatigue=home_fatigue,
            away_pitcher=away_pitcher_score,
            home_pitcher=home_pitcher_score,
            away_bullpen=away_bullpen,
            home_bullpen=home_bullpen,
            moneyline=moneyline,
            away_offense=away_offense,
            home_offense=home_offense,
        )

        correlation = self.correlation.analyze(
            under_score=scored["total_score"],
            home_dog_score=dog_data["home_dog_score"],
            away_dog_score=dog_data["away_dog_score"],
            line_movement=line_movement,
            series_game_number=series_game,
        )

        # EDGE plays — NRFI, F5, Team Totals, best prices
        full_total = line_movement.get("closing_total")
        nrfi = self.edge.score_nrfi(
            away_pitcher=away_pitcher_score,
            home_pitcher=home_pitcher_score,
            away_offense=away_offense,
            home_offense=home_offense,
            umpire_data=umpire_data,
            weather_data=weather_data,
            park_data=park_data,
        )
        f5 = self.edge.score_f5(
            away_pitcher=away_pitcher_score,
            home_pitcher=home_pitcher_score,
            away_offense=away_offense,
            home_offense=home_offense,
            park_data=park_data,
            weather_data=weather_data,
            umpire_data=umpire_data,
            full_game_total=full_total,
        )
        late_innings = self.edge.score_late_innings(
            away_pitcher=away_pitcher_score,
            home_pitcher=home_pitcher_score,
            away_bullpen=away_bullpen,
            home_bullpen=home_bullpen,
            away_offense=away_offense,
            home_offense=home_offense,
            park_data=park_data,
            weather_data=weather_data,
            umpire_data=umpire_data,
            full_game_total=full_total,
        )
        team_totals = self.edge.score_team_totals(
            away_team=away_team_name,
            home_team=home_team_name,
            away_offense=away_offense,
            home_offense=home_offense,
            away_pitcher=away_pitcher_score,
            home_pitcher=home_pitcher_score,
            away_bullpen=away_bullpen,
            home_bullpen=home_bullpen,
            park_data=park_data,
            weather_data=weather_data,
            full_game_total=full_total,
        )
        best_prices = self.line_svc.best_prices(current_lines, away_team_name, home_team_name)

        # ── Lock closing scores ───────────────────────────────────────────────
        # Once a game goes Live, the scoring snapshot is frozen. Closing
        # under_score, dog_score, NRFI, F5, etc. are all locked.
        closing_snapshot = {
            "under_score": scored["total_score"],
            "verdict": scored["verdict"],
            "park_factor_score": scored.get("park_factor_score"),
            "pitcher_score": scored.get("pitcher_score"),
            "weather_score": scored.get("weather_score"),
            "umpire_score": scored.get("umpire_score"),
            "bullpen_score": scored.get("bullpen_score"),
            "fatigue_score": scored.get("fatigue_score"),
            "line_movement_score": scored.get("line_movement_score"),
            "away_offense_score": scored.get("away_offense_score"),
            "home_offense_score": scored.get("home_offense_score"),
            "dog_score_data": dog_data,
            "nrfi": nrfi,
            "f5": f5,
            "late_innings": late_innings,
            "team_totals": team_totals,
        }
        locked = self.lock.get_or_lock(game_pk, game_state, closing_snapshot)

        # ── Live adjustments (only when game is Live) ────────────────────────
        live_score = game.get("live_score") or {}
        if game_state == "Live":
            live_under = self.live_adj.adjust_under(
                closing_under_score=locked["under_score"],
                live_data=live_score,
                closing_total=line_movement.get("closing_total"),
            )
            actual_dog_side = dog_data.get("actual_dog_side")
            closing_dog_score = locked["dog_score_data"].get(f"{actual_dog_side}_dog_score", 0) if actual_dog_side else 0
            live_dog = self.live_adj.adjust_dog(
                closing_dog_score=closing_dog_score,
                live_data=live_score,
                dog_side=actual_dog_side,
            )
        else:
            live_under = {"live_under_score": None, "delta": 0.0, "pace_note": None}
            live_dog = {"live_dog_score": None, "delta": 0.0, "pace_note": None}

        return {
            **game,
            **scored,
            "park_factor_data":    park_data,
            "pitcher_data":        {"away": away_pitcher_score, "home": home_pitcher_score},
            "pitcher_raw":         {"away": away_pitcher, "home": home_pitcher},
            "platoon_data":        {"away": away_platoon, "home": home_platoon},
            "recent_form_data":    {"away": away_recent_form, "home": home_recent_form},
            "weather_data":        weather_data,
            "umpire_data":         umpire_data,
            "bullpen_data":        {"away": away_bullpen, "home": home_bullpen},
            "fatigue_data":        {"away": away_fatigue, "home": home_fatigue},
            "offense_data":        {"away": away_offense, "home": home_offense},
            "line_movement":       line_movement,
            "moneyline_data":      moneyline,
            "dog_score":           dog_data,
            "correlation":         correlation,
            "nrfi":                nrfi,
            "f5":                  f5,
            "late_innings":        late_innings,
            "team_totals":         team_totals,
            "closing_locked":      locked,
            "live_under":          live_under,
            "live_dog":            live_dog,
            "best_prices":         best_prices,
            "series_game_number":  series_game,
            "games_in_series":     game.get("games_in_series", 3),
            "is_data_complete":    all([park_data, weather_data]),
        }


def _apply_pitcher_adjustments(
    pitcher: dict[str, Any],
    platoon: dict[str, Any],
    recent_form: dict[str, Any],
) -> dict[str, Any]:
    """Merge platoon matchup and recent trend adjustments into the pitcher score dict."""
    base = pitcher.get("under_score", 5.0)
    platoon_adj = platoon.get("adjustment", 0.0) if platoon else 0.0
    form_adj = recent_form.get("under_score_adj", 0.0) if recent_form else 0.0
    adjusted = round(min(10.0, max(0.0, base + platoon_adj + form_adj)), 2)
    return {
        **pitcher,
        "under_score": adjusted,
        "platoon_adjustment": round(platoon_adj, 2),
        "recent_form_adjustment": round(form_adj, 2),
        "recent_trend": recent_form.get("trend", "neutral") if recent_form else "neutral",
        "platoon_notes": platoon.get("notes", "") if platoon else "",
    }
