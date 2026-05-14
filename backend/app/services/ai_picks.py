from typing import Any, Optional


class AIPicksEngine:
    """
    Synthesizes every signal into ranked plain-English recommendations:
      - Top under plays with reasoning
      - WAY UNDER candidates (multiple converging signals)
      - Top dog upset candidates with reasoning
      - 3-4 leg parlay built from the day's best plays
    """

    def analyze_slate(self, games: list[dict[str, Any]]) -> dict[str, Any]:
        # Only Preview games — locked plays, no in-progress noise
        preview = [g for g in games if g.get("abstract_state") == "Preview"]
        if not preview:
            return self._empty()

        flagged = self._flag_suspicious_lines(preview)
        flagged_pks = {f["game_pk"] for f in flagged}
        clean = [g for g in preview if g.get("game_pk") not in flagged_pks]

        top_unders = self._rank_unders(clean)
        way_unders = self._find_way_unders(clean)
        top_dogs = self._rank_dogs(clean)
        top_overs = self._rank_overs(clean)
        top_faves = self._rank_faves(clean)
        safe_play = self._identify_safe_play(clean, top_unders)
        parlay = self._build_smart_parlay(safe_play, top_unders, top_dogs, way_unders)
        power_parlay = self._build_power_parlay(top_overs, top_faves)
        tease_parlay = self._build_tease_parlay(top_unders, top_dogs)
        pleaser_parlay = self._build_pleaser_parlay(top_unders, top_dogs, top_faves)
        out_the_park_parlay = self._build_out_the_park_parlay(top_unders, top_dogs, top_faves)
        way_out_the_park_parlay = self._build_way_out_the_park_parlay(top_unders, top_dogs, top_faves)
        longshot_parlay = self._build_longshot_parlay(top_dogs, way_unders, top_unders, top_overs)
        rankings = self._rank_full_board(preview, flagged_pks)
        watch_list = self._build_watch_list(clean)
        skip_list = self._build_skip_list(clean)

        def _strip(items):
            return [{k: v for k, v in item.items() if k != "_game"} for item in items]

        return {
            "safe_play": _strip([safe_play])[0] if safe_play else None,
            "top_unders": _strip(top_unders[:5]),
            "way_under_candidates": _strip(way_unders),
            "top_dogs": _strip(top_dogs[:5]),
            "top_overs": _strip(top_overs[:5]),
            "top_faves": _strip(top_faves[:5]),
            "parlay": parlay,
            "power_parlay": power_parlay,
            "tease_parlay": tease_parlay,
            "pleaser_parlay": pleaser_parlay,
            "out_the_park_parlay": out_the_park_parlay,
            "way_out_the_park_parlay": way_out_the_park_parlay,
            "longshot_parlay": longshot_parlay,
            "rankings": rankings,
            "watch_list": watch_list,
            "skip_list": skip_list,
            "flagged_lines": flagged,
            "total_preview_games": len(preview),
        }

    # ── Suspicious line detection ────────────────────────────────────────────

    def _flag_suspicious_lines(self, games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Detect Odds API entries that look corrupted or extreme."""
        flagged = []
        for g in games:
            lm = g.get("line_movement") or {}
            ml = g.get("moneyline_data") or {}
            total = lm.get("closing_total")
            away_ml = ml.get("closing_away_ml")
            home_ml = ml.get("closing_home_ml")

            issues = []
            # Total range: nearly all MLB totals fall between 6.5 and 12
            if total is not None and total < 6.0:
                issues.append(f"Total {total} unrealistically low")
            if total is not None and total > 13.0:
                issues.append(f"Total {total} unrealistically high")
            # ML disparity: huge ML mismatch is almost always bad data in baseball
            if away_ml is not None and home_ml is not None:
                if abs(away_ml) > 800 or abs(home_ml) > 800:
                    issues.append(f"ML extreme ({away_ml}/{home_ml}) — likely stale/corrupt feed")

            if issues:
                flagged.append({
                    "game_pk": g.get("game_pk"),
                    "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                    "closing_total": total,
                    "issues": issues,
                    "note": "Re-check once cleaner lines post",
                })
        return flagged

    # ── Safe Play of the Day ─────────────────────────────────────────────────

    def _identify_safe_play(
        self, games: list[dict[str, Any]], ranked_unders: list[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        """
        Highest-conviction under: BOTH starters elite + high NRFI + no hot offense vs fav SP.
        Returns the best candidate as a parlay-style leg dict.
        """
        candidates = []
        for u in ranked_unders:
            g = u.get("_game") or {}
            ap = (g.get("pitcher_data") or {}).get("away") or {}
            hp = (g.get("pitcher_data") or {}).get("home") or {}
            nrfi = (g.get("nrfi") or {}).get("nrfi_probability", 0)
            offense = g.get("offense_data") or {}
            ap_era = self._safe_float(ap.get("era"))
            hp_era = self._safe_float(hp.get("era"))
            if ap_era is None or hp_era is None:
                continue
            hot_count = sum(1 for s in ("away", "home") if (offense.get(s) or {}).get("streak") == "hot")
            score = u.get("under_score", 0)

            # Safe-play criteria: both SP under 3.5 ERA, NRFI >= 60, under_score >= 55, no two hot offenses
            if ap_era <= 3.50 and hp_era <= 3.50 and nrfi >= 60 and score >= 55 and hot_count <= 1:
                # Conviction = NRFI + (avg ERA gap to 4.50) + score
                era_quality = (4.50 - ((ap_era + hp_era) / 2)) * 10  # ~10 per full ERA below 4.5
                conviction = score + nrfi + era_quality - (hot_count * 8)
                candidates.append((conviction, u))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        winner = candidates[0][1]
        leg = self._under_leg(winner)
        leg["is_safe_play"] = True
        leg["confidence_label"] = "SAFEST PLAY ON THE BOARD"
        # Why-it's-safe summary
        g = winner.get("_game") or {}
        ap = (g.get("pitcher_data") or {}).get("away") or {}
        hp = (g.get("pitcher_data") or {}).get("home") or {}
        nrfi = (g.get("nrfi") or {}).get("nrfi_probability", 0)
        leg["safe_summary"] = (
            f"{ap.get('name','TBD')} ({ap.get('era','?')}) and {hp.get('name','TBD')} "
            f"({hp.get('era','?')}) — both elite. NRFI {nrfi}%. "
            f"Total {winner.get('closing_total') if winner.get('closing_total') is not None else 'TBD'} is generous for this pitching quality."
        )
        return leg

    # ── Smart Parlay Builder ────────────────────────────────────────────────

    def _build_smart_parlay(
        self,
        safe_play: Optional[dict[str, Any]],
        unders: list[dict[str, Any]],
        dogs: list[dict[str, Any]],
        way_unders: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Structure: Leg 1 = Safe Play (anchor), Leg 2 = best Under, Leg 3 = Dog +1.5/ML, Leg 4 = Under or Way Under.
        """
        legs: list[dict[str, Any]] = []
        used: set[str] = set()

        if safe_play:
            legs.append({**safe_play, "leg_role": "🔒 SAFE PLAY"})
            used.add(safe_play["matchup"])

        for u in unders:
            if u["matchup"] not in used and u.get("under_score", 0) >= 58:
                leg = self._under_leg(u)
                leg["leg_role"] = "📉 UNDER"
                legs.append(leg)
                used.add(u["matchup"])
                break

        for d in dogs:
            if d["matchup"] not in used and d.get("dog_score", 0) >= 60:
                leg = self._dog_leg(d)
                # Recommend +1.5 RL when ML is short or dog score is moderate
                ml = d.get("moneyline") or 150
                if ml <= 130 and d.get("dog_score", 0) >= 70:
                    leg["leg_role"] = f"🐕 {d['dog_team'].split()[-1].upper()} ML or +1.5 RL"
                else:
                    leg["leg_role"] = f"🐕 {d['dog_team'].split()[-1].upper()} +1.5 RL (safer)"
                legs.append(leg)
                used.add(d["matchup"])
                break

        # Leg 4: another under (way under preferred for the bonus payout)
        seed4 = None
        for w in way_unders:
            if w["matchup"] not in used:
                seed4 = w
                break
        if not seed4:
            for u in unders:
                if u["matchup"] not in used and u.get("under_score", 0) >= 56:
                    seed4 = u
                    break
        if seed4 and len(legs) < 4:
            leg = self._under_leg(seed4)
            leg["leg_role"] = "📉 UNDER"
            legs.append(leg)
            used.add(seed4["matchup"])

        if not legs:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "note": "No qualifying plays for parlay", "structure": ""}

        combined_american, payout = self._calc_parlay_odds([leg["odds"] for leg in legs])
        structure_parts = [leg.get("leg_role", "?") for leg in legs]
        return {
            "legs": legs,
            "combined_odds": combined_american,
            "payout_per_100": round(payout * 100, 2),
            "note": f"{len(legs)}-leg structured parlay: anchor + value legs",
            "structure": " + ".join(structure_parts),
        }

    # ── Full Board Rankings ──────────────────────────────────────────────────

    def _rank_full_board(
        self, games: list[dict[str, Any]], flagged_pks: set
    ) -> list[dict[str, Any]]:
        """One-line edge call for every game on the slate."""
        rows = []
        for g in games:
            game_pk = g.get("game_pk")
            if game_pk in flagged_pks:
                rows.append({
                    "game_pk": game_pk,
                    "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                    "play": "SKIP — bad data",
                    "edge_note": "Lines look corrupted, re-check later",
                    "tier": "skip",
                })
                continue

            score = g.get("total_score", 0)
            verdict = g.get("verdict", "Skip")
            dog = g.get("dog_score") or {}
            actual_dog = dog.get("actual_dog_side")
            dog_score = dog.get(f"{actual_dog}_dog_score", 0) if actual_dog else 0
            total = (g.get("line_movement") or {}).get("closing_total")
            total_str = total if total is not None else "TBD"
            ap = (g.get("pitcher_data") or {}).get("away") or {}
            hp = (g.get("pitcher_data") or {}).get("home") or {}
            ap_era = self._safe_float(ap.get("era"))
            hp_era = self._safe_float(hp.get("era"))

            if score >= 70:
                rows.append({"game_pk": game_pk, "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                             "play": f"UNDER {total_str}", "edge_note": f"Lock-tier under ({score:.0f})", "tier": "lock"})
            elif score >= 60:
                pitching = []
                if ap_era and ap_era <= 3.5: pitching.append(f"{ap.get('name','away SP')} {ap_era}")
                if hp_era and hp_era <= 3.5: pitching.append(f"{hp.get('name','home SP')} {hp_era}")
                note = f"Strong under — {', '.join(pitching)}" if pitching else f"Strong under ({score:.0f})"
                rows.append({"game_pk": game_pk, "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                             "play": f"UNDER {total_str}", "edge_note": note, "tier": "strong"})
            elif dog_score >= 65 and actual_dog:
                dog_team = g.get(f"{actual_dog}_team")
                dog_ml = (g.get("moneyline_data") or {}).get(f"closing_{actual_dog}_ml")
                ml_str = f" ({dog_ml:+d})" if dog_ml else ""
                rows.append({"game_pk": game_pk, "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                             "play": f"{dog_team} ML/+1.5{ml_str}",
                             "edge_note": f"Dog play — score {dog_score:.0f}", "tier": "dog"})
            elif score >= 55:
                rows.append({"game_pk": game_pk, "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                             "play": f"UNDER {total_str} lean", "edge_note": f"Mild lean ({score:.0f})", "tier": "lean"})
            else:
                rows.append({"game_pk": game_pk, "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                             "play": "PASS", "edge_note": f"No edge ({verdict}, score {score:.0f})", "tier": "skip"})
        # Sort by tier strength
        tier_order = {"lock": 0, "strong": 1, "dog": 2, "lean": 3, "skip": 4}
        rows.sort(key=lambda r: tier_order.get(r["tier"], 5))
        return rows

    # ── Watch List & Skip List ──────────────────────────────────────────────

    def _build_watch_list(self, games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Games where the model sees value but the line/data needs to firm up."""
        out = []
        for g in games:
            pitcher = g.get("pitcher_data") or {}
            ap = pitcher.get("away") or {}
            hp = pitcher.get("home") or {}
            ml = g.get("moneyline_data") or {}
            ap_era = self._safe_float(ap.get("era"))
            hp_era = self._safe_float(hp.get("era"))
            away_ml = ml.get("closing_away_ml")
            home_ml = ml.get("closing_home_ml")
            if ap_era is None or hp_era is None or away_ml is None or home_ml is None:
                continue

            # Look for ERA/ML mismatch — favorite has worse ERA than dog
            if away_ml < home_ml:  # away is fav
                if ap_era - hp_era >= 2.0:
                    out.append({
                        "game_pk": g.get("game_pk"),
                        "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                        "reason": f"Dog {hp.get('name','home SP')} ({hp_era}) priced behind worse-ERA favorite {ap.get('name','away SP')} ({ap_era})",
                        "watch_for": f"{g.get('home_team')} as a value dog at {home_ml:+d}",
                    })
            elif home_ml < away_ml:  # home is fav
                if hp_era - ap_era >= 2.0:
                    out.append({
                        "game_pk": g.get("game_pk"),
                        "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                        "reason": f"Dog {ap.get('name','away SP')} ({ap_era}) priced behind worse-ERA favorite {hp.get('name','home SP')} ({hp_era})",
                        "watch_for": f"{g.get('away_team')} as a value dog at {away_ml:+d}",
                    })
        return out[:5]

    def _build_skip_list(self, games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Games to actively avoid — explain why."""
        out = []
        for g in games:
            score = g.get("total_score", 0)
            offense = g.get("offense_data") or {}
            hot = [s for s in ("away", "home") if (offense.get(s) or {}).get("streak") == "hot"]
            pitcher = g.get("pitcher_data") or {}
            ap_era = self._safe_float((pitcher.get("away") or {}).get("era"))
            hp_era = self._safe_float((pitcher.get("home") or {}).get("era"))

            reasons = []
            if len(hot) == 2:
                reasons.append("Both offenses HOT — too much variance for under")
            if ap_era and hp_era and ap_era >= 5.0 and hp_era >= 5.0:
                reasons.append(f"Both SP weak (ERAs {ap_era}/{hp_era}) — under can't get carried")
            if score < 50:
                reasons.append(f"Model score {score:.0f} — no under edge")

            if reasons and score < 55:
                out.append({
                    "game_pk": g.get("game_pk"),
                    "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                    "reasons": reasons,
                })
        return out[:5]

    # ── Over recommendations ─────────────────────────────────────────────────

    def _rank_overs(self, games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Games likely to go OVER — fade the under model with hitter-friendly signals."""
        recs = []
        for g in games:
            offense = g.get("offense_data") or {}
            away_off = offense.get("away") or {}
            home_off = offense.get("home") or {}
            ap = (g.get("pitcher_data") or {}).get("away") or {}
            hp = (g.get("pitcher_data") or {}).get("home") or {}
            weather = g.get("weather_data") or {}
            park = g.get("park_factor_data") or {}
            lm = g.get("line_movement") or {}

            over_score = 50.0
            reasons = []

            # Both offenses hot
            hot_count = sum(1 for s in ("away", "home") if (offense.get(s) or {}).get("streak") == "hot")
            if hot_count == 2:
                over_score += 18
                reasons.append("Both offenses HOT — bats firing on both sides")
            elif hot_count == 1:
                over_score += 8
                hot_side = "away" if (away_off.get("streak") == "hot") else "home"
                hot_team = (g.get(f"{hot_side}_team") or "").split(" ")[-1]
                rpg = (offense.get(hot_side) or {}).get("runs_per_game_10d", "?")
                reasons.append(f"{hot_team} bats hot ({rpg} rpg L10)")

            # Combined RPG
            away_rpg = self._safe_float(away_off.get("runs_per_game_10d")) or 0
            home_rpg = self._safe_float(home_off.get("runs_per_game_10d")) or 0
            if away_rpg + home_rpg >= 11.5:
                over_score += 10
                reasons.append(f"Combined L10 offense {away_rpg + home_rpg:.1f} rpg")
            elif away_rpg + home_rpg >= 10.0:
                over_score += 5

            # Weak pitching
            ap_era = self._safe_float(ap.get("era"))
            hp_era = self._safe_float(hp.get("era"))
            if ap_era and hp_era and ap_era >= 5.0 and hp_era >= 5.0:
                over_score += 12
                reasons.append(f"Both SP weak ({ap_era}/{hp_era} ERA) — no stopper")
            elif (ap_era and ap_era >= 5.5) or (hp_era and hp_era >= 5.5):
                over_score += 6
                weakp = ap if (ap_era and ap_era >= 5.5) else hp
                reasons.append(f"{weakp.get('name','SP')} ({weakp.get('era','?')} ERA) vulnerable")

            # Hitter's park
            pf = park.get("park_factor")
            if pf and pf >= 110:
                over_score += 8
                reasons.append(f"Hitter's park ({pf} factor)")
            elif pf and pf >= 105:
                over_score += 5
                reasons.append(f"Slight hitter's lean ({pf} factor)")

            # Wind blowing OUT
            wind_dir = (weather.get("wind_dir") or "").lower()
            wind_mph = self._safe_float(weather.get("wind_mph")) or 0
            if wind_mph >= 12 and "out" in wind_dir:
                over_score += 10
                reasons.append(f"Wind blowing OUT at {wind_mph} mph")
            elif wind_mph >= 8 and "out" in wind_dir:
                over_score += 5

            # Warm temp
            temp = self._safe_float(weather.get("temp_f")) or 75
            if temp >= 88:
                over_score += 6
                reasons.append(f"Hot {temp:.0f}°F — ball flies")

            # Sharp UP move
            mv = self._safe_float(lm.get("movement")) or 0
            if mv >= 0.5:
                over_score += 6
                reasons.append(f"Line moved up {mv} — sharp on the over")

            # Penalize if main under model is strong
            score = g.get("total_score", 50)
            if score >= 65:
                over_score -= 10
            elif score >= 55:
                over_score -= 5

            over_score = max(0.0, min(100.0, over_score))
            if over_score < 55:
                continue
            # Skip games where the line never posted
            if lm.get("closing_total") is None:
                continue

            recs.append({
                "game_pk": g.get("game_pk"),
                "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                "closing_total": lm.get("closing_total"),
                "over_score": round(over_score, 1),
                "confidence": self._under_confidence(over_score),
                "verdict": self._over_verdict(over_score),
                "reasons": reasons[:5],
                "best_book": (g.get("best_prices", {}) or {}).get("best_over_book"),
                "best_price": (g.get("best_prices", {}) or {}).get("best_over_price"),
                "_game": g,
            })
        return sorted(recs, key=lambda x: x["over_score"], reverse=True)

    def _over_verdict(self, score: float) -> str:
        if score >= 78: return "OVER LOCK"
        if score >= 68: return "Strong OVER"
        if score >= 58: return "Lean OVER"
        return "Watch"

    # ── Favorite recommendations ─────────────────────────────────────────────

    def _rank_faves(self, games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Strong favorite plays — bet the chalk when the edge is real."""
        recs = []
        for g in games:
            ml = g.get("moneyline_data") or {}
            dog = g.get("dog_score") or {}
            actual_dog = dog.get("actual_dog_side")
            if not actual_dog:
                continue
            fav_side = "home" if actual_dog == "away" else "away"
            fav_team = g.get(f"{fav_side}_team")
            fav_ml = ml.get(f"closing_{fav_side}_ml")

            # Need a meaningful favorite line
            if fav_ml is None:
                continue
            # Skip absurd chalk (-700+) — no value, low payout, high risk
            if fav_ml <= -400:
                continue

            offense = g.get("offense_data") or {}
            fav_off = offense.get(fav_side) or {}
            opp_off = offense.get(actual_dog) or {}
            ap = (g.get("pitcher_data") or {}).get(fav_side) or {}
            opp_p = (g.get("pitcher_data") or {}).get(actual_dog) or {}
            bullpen = g.get("bullpen_data") or {}
            fav_pen = bullpen.get(fav_side) or {}
            opp_pen = bullpen.get(actual_dog) or {}

            fav_score = 50.0
            reasons = []

            # SP edge
            ap_era = self._safe_float(ap.get("era"))
            opp_era = self._safe_float(opp_p.get("era"))
            if ap_era is not None and opp_era is not None:
                era_gap = opp_era - ap_era
                if era_gap >= 2.0:
                    fav_score += min(era_gap * 7, 22)
                    reasons.append(f"SP edge — {ap.get('name','fav SP')} ({ap_era}) vs {opp_p.get('name','opp SP')} ({opp_era})")
                elif era_gap >= 1.0:
                    fav_score += 8
                    reasons.append(f"Slight SP edge ({ap_era} vs {opp_era} ERA)")

            # Hot fav offense
            if fav_off.get("streak") == "hot":
                fav_score += 12
                reasons.append(f"{fav_team.split(' ')[-1] if fav_team else 'Fav'} bats hot ({fav_off.get('runs_per_game_10d','?')} rpg L10)")

            # Cold opp offense
            if opp_off.get("streak") == "cold":
                fav_score += 10
                opp_team = g.get(f"{actual_dog}_team", "")
                reasons.append(f"{opp_team.split(' ')[-1]} cold ({opp_off.get('runs_per_game_10d','?')} rpg L10)")

            # Bullpen advantage
            fav_pen_fatigue = self._safe_float(fav_pen.get("pct_fatigued")) or 0
            opp_pen_fatigue = self._safe_float(opp_pen.get("pct_fatigued")) or 0
            if opp_pen_fatigue >= 0.5 and fav_pen_fatigue < 0.3:
                fav_score += 8
                reasons.append("Opposing pen gassed, fav pen fresh — late-game advantage")

            # Home field
            if fav_side == "home":
                fav_score += 4

            # Avoid laying chalk against ace
            if opp_era and opp_era <= 2.5:
                fav_score -= 8

            fav_score = max(0.0, min(100.0, fav_score))
            if fav_score < 55:
                continue

            implied = self._ml_to_implied(fav_ml)
            recs.append({
                "game_pk": g.get("game_pk"),
                "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                "fav_team": fav_team,
                "fav_side": fav_side,
                "fav_score": round(fav_score, 1),
                "moneyline": fav_ml,
                "implied_pct": implied,
                "verdict": self._fav_verdict(fav_score),
                "reasons": reasons[:5],
                "best_book": (g.get("best_prices", {}) or {}).get(f"best_{fav_side}_ml_book"),
                "best_price": (g.get("best_prices", {}) or {}).get(f"best_{fav_side}_ml"),
                "play_suggestion": self._fav_play_suggestion(fav_ml, fav_score),
                "_game": g,
            })
        return sorted(recs, key=lambda x: x["fav_score"], reverse=True)

    def _fav_verdict(self, score: float) -> str:
        if score >= 78: return "FAV LOCK"
        if score >= 68: return "Strong Fav"
        if score >= 58: return "Lean Fav"
        return "Watch"

    def _fav_play_suggestion(self, ml: float, score: float) -> str:
        """Given the price and confidence, recommend ML or -1.5 RL for value."""
        if ml is None:
            return "ML"
        # Heavy chalk: take -1.5 run line for plus money
        if ml <= -180 and score >= 65:
            return f"-1.5 RL (heavy chalk → run line for value)"
        if ml <= -200:
            return "-1.5 RL (avoid heavy chalk on ML)"
        return "ML"

    @staticmethod
    def _ml_to_implied(ml: float) -> float:
        if ml is None:
            return 0
        if ml < 0:
            return round(abs(ml) / (abs(ml) + 100) * 100, 1)
        return round(100 / (ml + 100) * 100, 1)

    @staticmethod
    def _ml_to_prob(ml: float) -> float:
        """American odds → decimal probability."""
        if ml is None:
            return 0.5
        if ml < 0:
            return abs(ml) / (abs(ml) + 100)
        return 100 / (ml + 100)

    @staticmethod
    def _prob_to_ml(prob: float) -> int:
        """Decimal probability → American odds (rounded)."""
        prob = max(0.02, min(0.98, prob))
        if prob >= 0.5:
            return -round(prob / (1 - prob) * 100)
        return round((1 - prob) / prob * 100)

    # Calibrated against real DraftKings MLB run-line / alt-total pricing
    def _estimate_fav_rl_odds(self, fav_ml: float) -> int:
        """
        Estimate -1.5 RL American odds for a favorite given their ML.
        Calibrated: -1.5 cover prob ≈ ML prob × 0.74.
        """
        if fav_ml is None:
            return 130
        fav_prob = self._ml_to_prob(fav_ml)
        rl_prob = fav_prob * 0.74
        return self._prob_to_ml(rl_prob)

    def _estimate_dog_rl_odds(self, dog_ml: float) -> int:
        """
        Estimate -1.5 RL American odds for an underdog (must win outright by 2+).
        Calibrated: dog winning by 2+ ≈ dog ML prob × 0.50.
        """
        if dog_ml is None:
            return 400
        dog_prob = self._ml_to_prob(dog_ml)
        rl_prob = dog_prob * 0.50
        return self._prob_to_ml(rl_prob)

    def _estimate_moved_under_odds(self, closing: float, moved: float) -> int:
        """
        Estimate UNDER American odds when the total is shifted down.
        Calibrated: each run shifted ≈ -7% probability change from -110 base.
        """
        if closing is None or moved is None:
            return 145
        base_prob = self._ml_to_prob(-110)  # 52.4% at -110 vig-included
        diff = closing - moved  # positive when moved is lower
        new_prob = base_prob - (diff * 0.07)
        return self._prob_to_ml(new_prob)

    def _estimate_moved_over_odds(self, closing: float, moved: float) -> int:
        """Estimate OVER odds when total is shifted UP."""
        if closing is None or moved is None:
            return 145
        base_prob = self._ml_to_prob(-110)
        diff = moved - closing
        new_prob = base_prob - (diff * 0.07)
        return self._prob_to_ml(new_prob)

    def _estimate_fav_alt_rl_odds(self, fav_ml: float, runs: float) -> int:
        """
        Alt-line favorite RL: -2.5, -3.5 etc. Win-by-N-or-more probability.
        Calibrated multipliers for typical MLB pricing:
          -1.5 → 0.74 of ML prob
          -2.5 → 0.45
          -3.5 → 0.27
        """
        if fav_ml is None:
            return 250
        fav_prob = self._ml_to_prob(fav_ml)
        if runs <= 1.5:
            mult = 0.74
        elif runs <= 2.5:
            mult = 0.45
        elif runs <= 3.5:
            mult = 0.27
        else:
            mult = 0.16
        return self._prob_to_ml(fav_prob * mult)

    # ── Power Parlay (Overs + Favorites) ─────────────────────────────────────

    def _build_power_parlay(
        self, overs: list[dict[str, Any]], faves: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Mirror of the value parlay but on the power side: best over + 1-2 favorites.
        """
        legs: list[dict[str, Any]] = []
        used: set[str] = set()

        # Leg 1: best over
        if overs:
            leg = self._over_leg(overs[0])
            leg["leg_role"] = "📈 BEST OVER"
            legs.append(leg)
            used.add(overs[0]["matchup"])

        # Leg 2: top favorite
        for f in faves:
            if f["matchup"] not in used:
                leg = self._fave_leg(f)
                leg["leg_role"] = f"⭐ {f['fav_team'].split()[-1].upper()} {f['play_suggestion']}"
                legs.append(leg)
                used.add(f["matchup"])
                break

        # Leg 3: second over if available
        for o in overs[1:]:
            if o["matchup"] not in used and o.get("over_score", 0) >= 60:
                leg = self._over_leg(o)
                leg["leg_role"] = "📈 OVER"
                legs.append(leg)
                used.add(o["matchup"])
                break

        # Leg 4: second favorite if available
        for f in faves[1:]:
            if f["matchup"] not in used and f.get("fav_score", 0) >= 60 and len(legs) < 4:
                leg = self._fave_leg(f)
                leg["leg_role"] = f"⭐ {f['fav_team'].split()[-1].upper()} {f['play_suggestion']}"
                legs.append(leg)
                used.add(f["matchup"])
                break

        if not legs:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "note": "No qualifying over/fave plays", "structure": ""}

        combined_american, payout = self._calc_parlay_odds([leg["odds"] for leg in legs])
        return {
            "legs": legs,
            "combined_odds": combined_american,
            "payout_per_100": round(payout * 100, 2),
            "note": f"{len(legs)}-leg POWER parlay — overs and favorites",
            "structure": " + ".join(leg.get("leg_role", "?") for leg in legs),
        }

    def _over_leg(self, o: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "OVER",
            "play": f"OVER {o.get('closing_total') if o.get('closing_total') is not None else 'TBD'}",
            "matchup": o["matchup"],
            "reasoning": " · ".join(o["reasons"][:3]) if o.get("reasons") else "Over model lean",
            "odds": -110,
            "best_book": o.get("best_book"),
            "best_price": o.get("best_price"),
            "over_reasons": o.get("reasons", []),
        }

    def _fave_leg(self, f: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "ML",
            "play": f"{f['fav_team']} {f.get('play_suggestion','ML')}",
            "matchup": f["matchup"],
            "reasoning": " · ".join(f["reasons"][:2]) if f.get("reasons") else f.get("verdict",""),
            "odds": f["moneyline"] if f["moneyline"] is not None else -150,
            "best_book": f.get("best_book"),
            "best_price": f.get("best_price"),
            "implied_pct": f.get("implied_pct"),
            "fav_reasons": f.get("reasons", []),
        }

    # ── Tease Parlay (1-run teaser, unders + dogs) ───────────────────────────

    # 4-team 1-run MLB teaser pricing (DraftKings consensus): roughly +160
    # 3-team 1-run teaser: roughly +100
    # 5-team 1-run teaser: roughly +260
    _TEASER_ODDS = {3: 100, 4: 160, 5: 260, 6: 400}
    _TEASE_AMOUNT = 1.0  # runs

    def _build_tease_parlay(
        self, top_unders: list[dict[str, Any]], top_dogs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        4-leg 1-run teaser: 2 unders teased UP +1 run, 2 dogs teased to +2.5 RL.
        Higher hit-rate, capped payout. Each leg is a play you'd ALSO take straight.
        """
        legs: list[dict[str, Any]] = []
        used: set[str] = set()

        # Dogs first — fewer candidates usually, so they get priority on shared games
        # Up to 2 dogs teased from +1.5 to +2.5 RL
        for d in top_dogs:
            if d["matchup"] in used:
                continue
            if d.get("dog_score", 0) < 55:
                continue
            teased_rl = 1.5 + self._TEASE_AMOUNT
            legs.append({
                "type": "TEASE_RL",
                "play": f"{d['dog_team']} +{teased_rl} RL",
                "matchup": d["matchup"],
                "original_line": "+1.5",
                "teased_line": f"+{teased_rl}",
                "tease_direction": f"+{self._TEASE_AMOUNT} (extra cushion)",
                "reasoning": " · ".join((d.get("reasons") or [])[:2]) if d.get("reasons") else d.get("verdict", ""),
                "dog_team": d["dog_team"],
                "best_book": d.get("best_book"),
            })
            used.add(d["matchup"])
            if sum(1 for l in legs if l["type"] == "TEASE_RL") >= 2:
                break

        # Then unders teased UP by 1 run from games not already used by dogs
        # Aim for 4 total legs (best teaser payout)
        for u in top_unders:
            if u["matchup"] in used:
                continue
            if u.get("under_score", 0) < 55:
                continue
            closing = u.get("closing_total")
            if closing is None:
                continue
            teased = round(closing + self._TEASE_AMOUNT, 1)
            legs.append({
                "type": "TEASE_UNDER",
                "play": f"UNDER {teased}",
                "matchup": u["matchup"],
                "original_line": closing,
                "teased_line": teased,
                "tease_direction": f"+{self._TEASE_AMOUNT} (cushion)",
                "reasoning": " · ".join((u.get("reasons") or [])[:2]) if u.get("reasons") else u.get("verdict", ""),
                "best_book": u.get("best_book"),
            })
            used.add(u["matchup"])
            if len(legs) >= 4:
                break

        if len(legs) < 3:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "structure": "", "note": "Need at least 3 qualifying legs for a teaser",
                    "tease_amount": f"{self._TEASE_AMOUNT} run"}

        odds = self._TEASER_ODDS.get(len(legs), 160)
        payout_per_100 = odds if odds > 0 else round(100 / abs(odds) * 100, 2)
        combined = f"+{odds}" if odds > 0 else f"{odds}"

        structure = " + ".join(
            "📉 U+1" if l["type"] == "TEASE_UNDER"
            else f"🐕 {l.get('dog_team','').split()[-1]} +2.5 RL"
            for l in legs
        )

        return {
            "legs": legs,
            "combined_odds": combined,
            "payout_per_100": payout_per_100,
            "tease_amount": f"{self._TEASE_AMOUNT} run",
            "structure": structure,
            "note": f"{len(legs)}-leg {self._TEASE_AMOUNT}-run teaser — moves every line in your favor",
        }

    # ── Pleaser Parlay (reverse teaser — lines moved AGAINST you, huge payout) ──

    # MLB pleaser pricing (consensus across DraftKings/MGM):
    # 2-leg 1-run pleaser: roughly +600
    # 3-leg 1-run pleaser: roughly +1500
    # 4-leg 1-run pleaser: roughly +3500
    # 5-leg 1-run pleaser: roughly +8000
    _PLEASER_ODDS = {2: 600, 3: 1500, 4: 3500, 5: 8000}
    _PLEASE_AMOUNT = 1.0  # runs

    def _build_pleaser_parlay(
        self,
        top_unders: list[dict[str, Any]],
        top_dogs: list[dict[str, Any]],
        top_faves: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Reverse teaser: every line moves AGAINST you. Way harder to hit, way bigger payout.
        ALWAYS produces 4 ranked legs (1-4 best→worst conviction). Backfills from any pool.
          - Unders moved DOWN 1 run (UNDER closing - 1)
          - Dogs taken at -1.5 RL (must WIN by 2+)
          - Faves taken at -1.5 RL (must win by 2+)
        """
        candidates: list[dict[str, Any]] = []

        # Pool every viable leg with a conviction score so we can rank 1-4
        # Conviction = base play strength - "pleaser penalty" for line difficulty
        for u in top_unders:
            closing = u.get("closing_total")
            if closing is None:
                continue
            moved = round(closing - self._PLEASE_AMOUNT, 1)
            if moved < 4.0:
                continue
            score = u.get("under_score", 0)
            conviction = score - 12
            leg_odds = self._estimate_moved_under_odds(closing, moved)
            candidates.append({
                "_conviction": conviction,
                "type": "PLEASE_UNDER",
                "play": f"UNDER {moved}",
                "matchup": u["matchup"],
                "original_line": closing,
                "moved_line": moved,
                "odds": leg_odds,
                "difficulty": f"Game must finish under {moved} (1 run tougher than {closing})",
                "reasoning": " · ".join((u.get("reasons") or [])[:2]) if u.get("reasons") else u.get("verdict", ""),
                "best_book": u.get("best_book"),
            })

        for d in top_dogs:
            score = d.get("dog_score", 0)
            conviction = score - 25
            leg_odds = self._estimate_dog_rl_odds(d.get("moneyline"))
            candidates.append({
                "_conviction": conviction,
                "type": "PLEASE_DOG_RL",
                "play": f"{d['dog_team']} -1.5 RL",
                "matchup": d["matchup"],
                "original_line": "+1.5 (cover)",
                "moved_line": "-1.5 (win by 2+)",
                "odds": leg_odds,
                "difficulty": "Dog must WIN OUTRIGHT BY 2+",
                "reasoning": " · ".join((d.get("reasons") or [])[:2]) if d.get("reasons") else d.get("verdict", ""),
                "dog_team": d["dog_team"],
                "best_book": d.get("best_book"),
            })

        for f in top_faves:
            score = f.get("fav_score", 0)
            conviction = score - 15
            leg_odds = self._estimate_fav_rl_odds(f.get("moneyline"))
            candidates.append({
                "_conviction": conviction,
                "type": "PLEASE_FAV_RL",
                "play": f"{f['fav_team']} -1.5 RL",
                "matchup": f["matchup"],
                "original_line": "ML",
                "moved_line": "-1.5 (win by 2+)",
                "odds": leg_odds,
                "difficulty": "Fav must WIN BY 2+ instead of just winning",
                "reasoning": " · ".join((f.get("reasons") or [])[:2]) if f.get("reasons") else f.get("verdict", ""),
                "fav_team": f["fav_team"],
                "best_book": f.get("best_book"),
            })

        if not candidates:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "structure": "", "note": "No qualifying plays for pleaser",
                    "please_amount": f"{self._PLEASE_AMOUNT} run"}

        # Rank by conviction descending — best chance to hit at #1, biggest stretch at #4
        candidates.sort(key=lambda x: x["_conviction"], reverse=True)

        legs: list[dict[str, Any]] = []
        used: set[str] = set()
        # Pick 4 legs from different games, in conviction order
        for c in candidates:
            if c["matchup"] in used:
                continue
            legs.append(c)
            used.add(c["matchup"])
            if len(legs) >= 4:
                break

        # Stamp ranks 1-4 onto the chosen legs
        for i, leg in enumerate(legs, start=1):
            leg["rank"] = i
            leg["rank_label"] = (
                "MOST LIKELY TO HIT" if i == 1
                else "STRONG SECOND" if i == 2
                else "STRETCH PLAY" if i == 3
                else "LONGSHOT KICKER"
            )
            leg.pop("_conviction", None)

        # Real parlay math: multiply per-leg American odds for realistic combined price
        combined_american, payout = self._calc_parlay_odds([l["odds"] for l in legs])

        structure_parts = []
        for l in legs:
            tag = (
                f"🐕 {l.get('dog_team','').split()[-1]} -1.5" if l["type"] == "PLEASE_DOG_RL"
                else f"⭐ {l.get('fav_team','').split()[-1]} -1.5" if l["type"] == "PLEASE_FAV_RL"
                else "📉 U-1"
            )
            structure_parts.append(f"#{l['rank']} {tag}")

        return {
            "legs": legs,
            "combined_odds": combined_american,
            "payout_per_100": round(payout * 100, 2),
            "please_amount": f"{self._PLEASE_AMOUNT} run",
            "structure": " · ".join(structure_parts),
            "note": f"{len(legs)}-leg {self._PLEASE_AMOUNT}-run PLEASER ranked 1→4 (most likely → biggest stretch)",
        }

    # ── Out The Park Parlay (extreme reverse tease — minimum -1.5 movement) ──

    # Out-the-park pricing — biggest swing on the slate
    # 4-leg 1.5-run pleaser is roughly 2.5-3x the 1-run pleaser
    _OUT_THE_PARK_ODDS = {2: 1200, 3: 3500, 4: 9000, 5: 22000}
    _OUT_THE_PARK_AMOUNT = 1.5  # minimum runs moved against you

    def _build_out_the_park_parlay(
        self,
        top_unders: list[dict[str, Any]],
        top_dogs: list[dict[str, Any]],
        top_faves: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        OUT THE PARK PARLAY — extreme reverse tease. Minimum 1.5 runs moved AGAINST you.
        Always 4 legs ranked 1→4. The biggest swing on the board.
          - Unders moved DOWN minimum 1.5 runs (UNDER closing - 1.5)
          - Dogs at -1.5 RL (must WIN OUTRIGHT BY 2+)
          - Faves at -1.5 RL (must WIN BY 2+)
        """
        candidates: list[dict[str, Any]] = []

        # Unders: shave 1.5 off the total, big penalty since this is brutal
        for u in top_unders:
            closing = u.get("closing_total")
            if closing is None:
                continue
            moved = round(closing - self._OUT_THE_PARK_AMOUNT, 1)
            if moved < 4.0:  # don't recommend absurd totals
                continue
            score = u.get("under_score", 0)
            # Under -1.5 penalty: ~20 conviction points (much harder than -1)
            conviction = score - 20
            leg_odds = self._estimate_moved_under_odds(closing, moved)
            candidates.append({
                "_conviction": conviction,
                "type": "OTP_UNDER",
                "play": f"UNDER {moved}",
                "matchup": u["matchup"],
                "original_line": closing,
                "moved_line": moved,
                "odds": leg_odds,
                "difficulty": f"Game must finish under {moved} (1.5 runs tougher than {closing})",
                "reasoning": " · ".join((u.get("reasons") or [])[:2]) if u.get("reasons") else u.get("verdict", ""),
                "best_book": u.get("best_book"),
            })

        # Dogs at -1.5 RL — must win outright by 2+
        for d in top_dogs:
            score = d.get("dog_score", 0)
            # Brutal jump from "cover +1.5" to "win by 2+": 30 point penalty
            conviction = score - 30
            leg_odds = self._estimate_dog_rl_odds(d.get("moneyline"))
            candidates.append({
                "_conviction": conviction,
                "type": "OTP_DOG_RL",
                "play": f"{d['dog_team']} -1.5 RL",
                "matchup": d["matchup"],
                "original_line": "+1.5 (cover)",
                "moved_line": "-1.5 (win by 2+)",
                "odds": leg_odds,
                "difficulty": "Underdog must WIN OUTRIGHT BY 2+ runs",
                "reasoning": " · ".join((d.get("reasons") or [])[:2]) if d.get("reasons") else d.get("verdict", ""),
                "dog_team": d["dog_team"],
                "best_book": d.get("best_book"),
            })

        # Faves at -1.5 RL — already-favored team must cover the runline by 2
        for f in top_faves:
            score = f.get("fav_score", 0)
            # Fav ML → -1.5 RL: 18 point penalty
            conviction = score - 18
            leg_odds = self._estimate_fav_rl_odds(f.get("moneyline"))
            candidates.append({
                "_conviction": conviction,
                "type": "OTP_FAV_RL",
                "play": f"{f['fav_team']} -1.5 RL",
                "matchup": f["matchup"],
                "original_line": "ML",
                "moved_line": "-1.5 (win by 2+)",
                "odds": leg_odds,
                "difficulty": "Favorite must WIN BY 2+ runs (no late comeback by dog)",
                "reasoning": " · ".join((f.get("reasons") or [])[:2]) if f.get("reasons") else f.get("verdict", ""),
                "fav_team": f["fav_team"],
                "best_book": f.get("best_book"),
            })

        if not candidates:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "structure": "", "note": "No qualifying plays for Out The Park",
                    "otp_amount": f"{self._OUT_THE_PARK_AMOUNT} runs"}

        # Rank by conviction descending
        candidates.sort(key=lambda x: x["_conviction"], reverse=True)

        legs: list[dict[str, Any]] = []
        used: set[str] = set()
        for c in candidates:
            if c["matchup"] in used:
                continue
            legs.append(c)
            used.add(c["matchup"])
            if len(legs) >= 4:
                break

        # Stamp ranks 1-4 with vivid labels for the biggest swing of the day
        for i, leg in enumerate(legs, start=1):
            leg["rank"] = i
            leg["rank_label"] = (
                "BEST SHOT" if i == 1
                else "STILL ALIVE" if i == 2
                else "MOON SHOT" if i == 3
                else "OUT THE PARK"
            )
            leg.pop("_conviction", None)

        # Real parlay math: multiply per-leg American odds for realistic combined price
        combined_american, payout = self._calc_parlay_odds([l["odds"] for l in legs])

        structure_parts = []
        for l in legs:
            tag = (
                f"🐕 {l.get('dog_team','').split()[-1]} -1.5" if l["type"] == "OTP_DOG_RL"
                else f"⭐ {l.get('fav_team','').split()[-1]} -1.5" if l["type"] == "OTP_FAV_RL"
                else "📉 U-1.5"
            )
            structure_parts.append(f"#{l['rank']} {tag}")

        return {
            "legs": legs,
            "combined_odds": combined_american,
            "payout_per_100": round(payout * 100, 2),
            "otp_amount": f"{self._OUT_THE_PARK_AMOUNT} runs",
            "structure": " · ".join(structure_parts),
            "note": f"{len(legs)}-leg OUT THE PARK — minimum 1.5 runs moved against you. The biggest swing of the day.",
        }

    # ── WAY OUT THE PARK Parlay (extreme reverse — faves -2.5, dogs -1.5, unders -2) ──

    _WOTP_FAV_RUNS = 2.5  # faves must win by 3+
    _WOTP_DOG_RUNS = 1.5  # dogs must still win by 2+ (max realistic)
    _WOTP_UNDER_RUNS = 2.0  # unders moved down 2 runs

    def _build_way_out_the_park_parlay(
        self,
        top_unders: list[dict[str, Any]],
        top_dogs: list[dict[str, Any]],
        top_faves: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        WAY OUT THE PARK — the biggest swing on the slate.
          - Faves at -2.5 RL (must WIN BY 3+)
          - Dogs at -1.5 RL (must WIN OUTRIGHT BY 2+)
          - Unders moved DOWN 2 runs minimum
        Always 4 ranked legs, real per-leg American odds, real parlay math.
        """
        candidates: list[dict[str, Any]] = []

        # Unders: shave 2 runs off the total
        for u in top_unders:
            closing = u.get("closing_total")
            if closing is None:
                continue
            moved = round(closing - self._WOTP_UNDER_RUNS, 1)
            if moved < 4.0:
                continue
            score = u.get("under_score", 0)
            conviction = score - 28  # -2 runs is brutal
            leg_odds = self._estimate_moved_under_odds(closing, moved)
            candidates.append({
                "_conviction": conviction,
                "type": "WOTP_UNDER",
                "play": f"UNDER {moved}",
                "matchup": u["matchup"],
                "original_line": closing,
                "moved_line": moved,
                "odds": leg_odds,
                "difficulty": f"Game must finish under {moved} ({self._WOTP_UNDER_RUNS} runs tougher than {closing})",
                "reasoning": " · ".join((u.get("reasons") or [])[:2]) if u.get("reasons") else u.get("verdict", ""),
                "best_book": u.get("best_book"),
            })

        # Dogs at -1.5 RL — same as OTP (can't reasonably go to -2.5 for dogs)
        for d in top_dogs:
            score = d.get("dog_score", 0)
            conviction = score - 30
            leg_odds = self._estimate_dog_rl_odds(d.get("moneyline"))
            candidates.append({
                "_conviction": conviction,
                "type": "WOTP_DOG_RL",
                "play": f"{d['dog_team']} -1.5 RL",
                "matchup": d["matchup"],
                "original_line": "+1.5 (cover)",
                "moved_line": "-1.5 (win by 2+)",
                "odds": leg_odds,
                "difficulty": "Underdog must WIN OUTRIGHT BY 2+ runs",
                "reasoning": " · ".join((d.get("reasons") or [])[:2]) if d.get("reasons") else d.get("verdict", ""),
                "dog_team": d["dog_team"],
                "best_book": d.get("best_book"),
            })

        # Faves at -2.5 RL — must win by 3+
        for f in top_faves:
            score = f.get("fav_score", 0)
            conviction = score - 32  # -2.5 is the biggest favorite stretch
            leg_odds = self._estimate_fav_alt_rl_odds(f.get("moneyline"), self._WOTP_FAV_RUNS)
            candidates.append({
                "_conviction": conviction,
                "type": "WOTP_FAV_RL",
                "play": f"{f['fav_team']} -{self._WOTP_FAV_RUNS} RL",
                "matchup": f["matchup"],
                "original_line": "ML",
                "moved_line": f"-{self._WOTP_FAV_RUNS} (win by 3+)",
                "odds": leg_odds,
                "difficulty": f"Favorite must WIN BY 3+ runs (no late comeback by dog, no save situations)",
                "reasoning": " · ".join((f.get("reasons") or [])[:2]) if f.get("reasons") else f.get("verdict", ""),
                "fav_team": f["fav_team"],
                "best_book": f.get("best_book"),
            })

        if not candidates:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "structure": "", "note": "No qualifying plays for Way Out The Park"}

        # Rank by conviction descending
        candidates.sort(key=lambda x: x["_conviction"], reverse=True)

        legs: list[dict[str, Any]] = []
        used: set[str] = set()
        for c in candidates:
            if c["matchup"] in used:
                continue
            legs.append(c)
            used.add(c["matchup"])
            if len(legs) >= 4:
                break

        # Stamp ranks 1-4 with vivid labels
        for i, leg in enumerate(legs, start=1):
            leg["rank"] = i
            leg["rank_label"] = (
                "BEST SHOT" if i == 1
                else "STILL ALIVE" if i == 2
                else "MOON SHOT" if i == 3
                else "WAY OUT"
            )
            leg.pop("_conviction", None)

        # Real parlay math
        combined_american, payout = self._calc_parlay_odds([l["odds"] for l in legs])

        structure_parts = []
        for l in legs:
            tag = (
                f"🐕 {l.get('dog_team','').split()[-1]} -1.5" if l["type"] == "WOTP_DOG_RL"
                else f"⭐ {l.get('fav_team','').split()[-1]} -2.5" if l["type"] == "WOTP_FAV_RL"
                else "📉 U-2"
            )
            structure_parts.append(f"#{l['rank']} {tag}")

        return {
            "legs": legs,
            "combined_odds": combined_american,
            "payout_per_100": round(payout * 100, 2),
            "wotp_amount": "Faves -2.5 · Dogs -1.5 · Unders -2",
            "structure": " · ".join(structure_parts),
            "note": f"{len(legs)}-leg WAY OUT THE PARK — faves win by 3+, unders drop 2, dogs win outright by 2+. The wildest swing.",
        }

    # ── Longshot Parlay (high-EV legs, big payout) ───────────────────────────

    def _build_longshot_parlay(
        self,
        top_dogs: list[dict[str, Any]],
        way_unders: list[dict[str, Any]],
        top_unders: list[dict[str, Any]],
        top_overs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        5-leg longshot ticket:
          - 1-2 plus-money dogs (ML)
          - 1 way-under
          - 1 strongest under
          - 1 over OR another dog
        Aim for combined +800 to +5000.
        """
        legs: list[dict[str, Any]] = []
        used: set[str] = set()

        # Leg 1: best plus-money dog (the bigger the dog, the bigger the payout)
        plus_dogs = sorted(
            [d for d in top_dogs if d.get("moneyline") and d["moneyline"] >= 130],
            key=lambda d: -d.get("dog_score", 0),
        )
        if plus_dogs:
            d = plus_dogs[0]
            legs.append({
                "type": "ML",
                "play": f"{d['dog_team']} ML",
                "matchup": d["matchup"],
                "odds": d["moneyline"],
                "reasoning": " · ".join((d.get("reasons") or [])[:2]) if d.get("reasons") else d.get("verdict", ""),
                "best_book": d.get("best_book"),
                "leg_role": "🐕 BIG DOG",
            })
            used.add(d["matchup"])

        # Leg 2: way under (high signal convergence at -110)
        for w in way_unders:
            if w["matchup"] not in used:
                legs.append({
                    "type": "UNDER",
                    "play": f"UNDER {w.get('closing_total','TBD')}",
                    "matchup": w["matchup"],
                    "odds": -110,
                    "reasoning": f"{w.get('signal_count','?')} converging signals — high-EV under",
                    "best_book": w.get("best_book"),
                    "leg_role": "🔻🔻 WAY UNDER",
                })
                used.add(w["matchup"])
                break

        # Leg 3: strongest under
        for u in top_unders:
            if u["matchup"] not in used and u.get("under_score", 0) >= 60:
                leg = self._under_leg(u)
                leg["leg_role"] = "📉 STRONG UNDER"
                legs.append(leg)
                used.add(u["matchup"])
                break

        # Leg 4: another plus-money dog if available
        for d in plus_dogs[1:]:
            if d["matchup"] not in used and d.get("dog_score", 0) >= 60:
                legs.append({
                    "type": "ML",
                    "play": f"{d['dog_team']} ML",
                    "matchup": d["matchup"],
                    "odds": d["moneyline"],
                    "reasoning": " · ".join((d.get("reasons") or [])[:2]) if d.get("reasons") else d.get("verdict", ""),
                    "best_book": d.get("best_book"),
                    "leg_role": "🐕 SECOND DOG",
                })
                used.add(d["matchup"])
                break

        # Leg 5: best over for variance kicker
        for o in top_overs:
            if o["matchup"] not in used and o.get("over_score", 0) >= 60 and len(legs) < 5:
                leg = self._over_leg(o)
                leg["leg_role"] = "📈 OVER VARIANCE"
                legs.append(leg)
                used.add(o["matchup"])
                break

        # Backfill if still fewer than 4 legs — add another strong under
        if len(legs) < 4:
            for u in top_unders:
                if u["matchup"] not in used and u.get("under_score", 0) >= 56:
                    leg = self._under_leg(u)
                    leg["leg_role"] = "📉 UNDER"
                    legs.append(leg)
                    used.add(u["matchup"])
                    if len(legs) >= 4:
                        break

        if not legs:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "structure": "", "note": "No qualifying longshot legs"}

        combined, payout = self._calc_parlay_odds([l["odds"] for l in legs])
        structure = " + ".join(l.get("leg_role", "?") for l in legs)
        return {
            "legs": legs,
            "combined_odds": combined,
            "payout_per_100": round(payout * 100, 2),
            "structure": structure,
            "note": f"{len(legs)}-leg longshot — chase a 4-figure ticket with model-backed legs",
        }

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    # ── Under recommendations ────────────────────────────────────────────────

    def _rank_unders(self, games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sorted_g = sorted(games, key=lambda g: g.get("total_score", 0), reverse=True)
        recs = []
        for g in sorted_g:
            score = g.get("total_score", 0)
            if score < 55:
                continue
            # Skip games where the line never posted — can't recommend a play with no number
            closing = (g.get("line_movement") or {}).get("closing_total")
            if closing is None:
                continue
            recs.append({
                "game_pk": g.get("game_pk"),
                "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                "closing_total": closing,
                "under_score": score,
                "verdict": g.get("verdict"),
                "confidence": self._under_confidence(score),
                "reasons": self._under_reasons(g),
                "best_book": g.get("best_prices", {}).get("best_under_book"),
                "best_price": g.get("best_prices", {}).get("best_under_price"),
                "_game": g,
            })
        return recs

    def _under_reasons(self, g: dict[str, Any]) -> list[str]:
        reasons = []
        park_data = g.get("park_factor_data") or {}
        if g.get("park_factor_score", 5) >= 7 and park_data.get("park_factor"):
            reasons.append(f"Pitcher's park ({park_data['park_factor']} factor)")
        if g.get("pitcher_score", 5) >= 6.5:
            ap = (g.get("pitcher_data") or {}).get("away") or {}
            hp = (g.get("pitcher_data") or {}).get("home") or {}
            reasons.append(f"Strong arms: {ap.get('name','TBD')} {ap.get('era','?')} vs {hp.get('name','TBD')} {hp.get('era','?')}")
        if g.get("weather_score", 5) >= 6.5:
            reasons.append("Weather suppresses scoring")
        if g.get("fatigue_score", 5) >= 7:
            reasons.append("Fatigued offenses (rest/travel)")

        offense = g.get("offense_data", {})
        for side in ("away", "home"):
            o = offense.get(side, {})
            if o.get("streak") == "cold":
                team_short = (g.get(f"{side}_team") or "").split(" ")[-1]
                reasons.append(f"{team_short} bats cold ({o.get('runs_per_game_10d','?')} rpg L10)")

        nrfi = g.get("nrfi", {}).get("nrfi_probability", 0)
        if nrfi >= 60:
            reasons.append(f"NRFI prob {nrfi}%")

        lm = g.get("line_movement", {})
        if (lm.get("movement") or 0) <= -0.5:
            reasons.append(f"Sharp under move ({lm.get('movement')})")

        return reasons[:5]

    # ── WAY UNDER candidates ─────────────────────────────────────────────────

    def _find_way_unders(self, games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Multiple independent signals converging = high probability of WAY under (game ends 2+ runs under the total)."""
        recs = []
        for g in games:
            signals = []
            score = g.get("total_score", 0)
            if score >= 70:
                signals.append(("Main model", f"{score} ({g.get('verdict')})"))
            if g.get("nrfi", {}).get("nrfi_probability", 0) >= 64:
                signals.append(("NRFI", f"{g['nrfi']['nrfi_probability']}%"))
            if g.get("f5", {}).get("f5_score", 0) >= 65:
                signals.append(("F5", f"{g['f5']['f5_score']}"))
            if g.get("late_innings", {}).get("late_score", 0) >= 60:
                signals.append(("Late/Pen", f"{g['late_innings']['late_score']}"))
            if g.get("team_totals", {}).get("best_score", 0) >= 65:
                signals.append(("TT", f"{g['team_totals']['best_team']} {g['team_totals']['best_score']}"))
            if (g.get("line_movement", {}).get("movement") or 0) <= -1:
                signals.append(("Sharp drop", f"{g['line_movement']['movement']}"))
            offense = g.get("offense_data", {})
            cold_count = sum(1 for s in ("away", "home") if (offense.get(s, {}) or {}).get("streak") == "cold")
            if cold_count == 2:
                signals.append(("Both cold", "L10 < 3.2 rpg both sides"))
            elif cold_count == 1:
                signals.append(("One cold", "1 side L10 < 3.2 rpg"))

            if len(signals) >= 3 and (g.get("line_movement") or {}).get("closing_total") is not None:
                recs.append({
                    "game_pk": g.get("game_pk"),
                    "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                    "closing_total": g.get("line_movement", {}).get("closing_total"),
                    "under_score": g.get("total_score", 0),
                    "signal_count": len(signals),
                    "converging_signals": [f"{k}: {v}" for k, v in signals],
                    "verdict": "WAY UNDER 🔻🔻",
                    "best_book": g.get("best_prices", {}).get("best_under_book"),
                    "best_price": g.get("best_prices", {}).get("best_under_price"),
                    "_game": g,
                })
        return sorted(recs, key=lambda x: x["signal_count"], reverse=True)[:3]

    # ── Dog recommendations ──────────────────────────────────────────────────

    def _rank_dogs(self, games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        recs = []
        for g in games:
            ds = g.get("dog_score", {}) or {}
            actual = ds.get("actual_dog_side")
            if not actual:
                continue
            dog_score = ds.get(f"{actual}_dog_score", 0)
            if dog_score < 60:
                continue

            ml = g.get("moneyline_data", {}) or {}
            dog_team = g.get(f"{actual}_team")
            dog_ml = ml.get(f"closing_{actual}_ml")

            reasons = []
            if dog_score >= 75:
                reasons.append("Strong upset profile")
            elif dog_score >= 65:
                reasons.append("Lean dog play")

            offense = (g.get("offense_data", {}) or {}).get(actual, {}) or {}
            if offense.get("streak") == "hot":
                reasons.append(f"Bats hot ({offense.get('runs_per_game_10d','?')} rpg L10)")

            opp_side = "home" if actual == "away" else "away"
            opp_off = (g.get("offense_data", {}) or {}).get(opp_side, {}) or {}
            if opp_off.get("streak") == "cold":
                opp_short = (g.get(f"{opp_side}_team") or "").split(" ")[-1]
                reasons.append(f"Favorite ({opp_short}) cold")

            opp_fatigue = (g.get("fatigue_data", {}) or {}).get(opp_side, {}) or {}
            if opp_fatigue.get("fatigue_score", 5) >= 7:
                reasons.append("Favorite fatigued")

            recs.append({
                "game_pk": g.get("game_pk"),
                "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                "dog_team": dog_team,
                "dog_side": actual,
                "dog_score": dog_score,
                "verdict": ds.get(f"{actual}_dog_verdict"),
                "moneyline": dog_ml,
                "reasons": reasons,
                "best_book": (g.get("best_prices", {}) or {}).get(f"best_{actual}_ml_book"),
                "best_price": (g.get("best_prices", {}) or {}).get(f"best_{actual}_ml"),
                "_game": g,
            })
        return sorted(recs, key=lambda x: x["dog_score"], reverse=True)

    def _under_leg(self, u: dict[str, Any]) -> dict[str, Any]:
        is_way = u.get("verdict", "").startswith("WAY")
        reasons = u.get("converging_signals") if is_way else u.get("reasons", [])
        game = u.get("_game") or {}
        return {
            "type": "UNDER",
            "play": f"UNDER {u.get('closing_total') if u.get('closing_total') is not None else 'TBD'}",
            "matchup": u["matchup"],
            "reasoning": " · ".join(reasons[:3]) if reasons else "Under model lean",
            "odds": -110,
            "best_book": u.get("best_book"),
            "best_price": u.get("best_price"),
            "projected_floor": self._project_floor(game, u.get("closing_total")),
            "floor_reasoning": self._floor_reasoning(game),
        }

    def _dog_leg(self, d: dict[str, Any]) -> dict[str, Any]:
        game = d.get("_game") or {}
        cover_analysis = self._dog_cover_analysis(game, d)
        return {
            "type": "ML",
            "play": f"{d['dog_team']} ML",
            "matchup": d["matchup"],
            "reasoning": f"{d['verdict']} · {' · '.join(d['reasons'][:2])}" if d.get("reasons") else d.get("verdict", ""),
            "odds": d["moneyline"] if d["moneyline"] is not None else 150,
            "best_book": d.get("best_book"),
            "best_price": d.get("best_price"),
            "cover_analysis": cover_analysis,
        }

    # ── Under floor projection ────────────────────────────────────────────────

    def _project_floor(self, game: dict[str, Any], closing_total: Optional[float]) -> Optional[str]:
        """Estimate the lowest plausible run total based on model signals."""
        if not closing_total or not game:
            return None

        score = game.get("total_score", 50)
        # Each 10 points above 50 shaves ~0.5 runs off the floor
        shave = ((score - 50) / 10) * 0.5
        floor = closing_total - shave

        # Pitcher quality boost
        pitcher_score = game.get("pitcher_score", 5)
        if pitcher_score >= 8:
            floor -= 0.5
        elif pitcher_score >= 6.5:
            floor -= 0.25

        # Both offenses cold
        offense = game.get("offense_data", {})
        cold_count = sum(1 for s in ("away", "home") if (offense.get(s) or {}).get("streak") == "cold")
        if cold_count == 2:
            floor -= 0.5

        # NRFI boosts floor confidence
        nrfi = game.get("nrfi", {}).get("nrfi_probability", 0)
        if nrfi >= 70:
            floor -= 0.25

        floor = max(floor, closing_total * 0.55)  # never project below 55% of total
        floor = round(floor * 2) / 2  # snap to nearest 0.5
        return f"{floor:.1f}"

    def _floor_reasoning(self, game: dict[str, Any]) -> list[str]:
        """Key driver bullets explaining why the game scores low."""
        if not game:
            return []
        notes = []

        ap = (game.get("pitcher_data") or {}).get("away") or {}
        hp = (game.get("pitcher_data") or {}).get("home") or {}
        if ap.get("name") and hp.get("name"):
            a_era = ap.get("era", "?")
            h_era = hp.get("era", "?")
            a_k = ap.get("k_per_9", "?")
            h_k = hp.get("k_per_9", "?")
            notes.append(
                f"{ap['name']} ({a_era} ERA, {a_k} K/9) vs {hp['name']} ({h_era} ERA, {h_k} K/9)"
            )

        park = (game.get("park_factor_data") or {})
        pf = park.get("park_factor")
        if pf and pf < 100:
            notes.append(f"Pitcher's park — {park.get('venue_name', 'venue')} suppresses run scoring ({pf} factor)")

        offense = game.get("offense_data") or {}
        for side in ("away", "home"):
            o = offense.get(side) or {}
            if o.get("streak") == "cold":
                team = (game.get(f"{side}_team") or "").split(" ")[-1]
                notes.append(f"{team} offense cold — {o.get('runs_per_game_10d', '?')} rpg over last 10")

        w = game.get("weather_data") or {}
        if (w.get("wind_mph") or 0) >= 10 and "in" in (w.get("wind_dir") or "").lower():
            notes.append(f"Wind blowing IN at {w['wind_mph']} mph — suppresses fly balls")
        elif (w.get("temp_f") or 75) < 55:
            notes.append(f"Cold {w['temp_f']}°F — heavy air, suppressed carry")

        nrfi = (game.get("nrfi") or {}).get("nrfi_probability", 0)
        if nrfi >= 65:
            notes.append(f"NRFI {nrfi}% — game likely scoreless through 1st inning")

        lm = game.get("line_movement") or {}
        if (lm.get("movement") or 0) <= -0.5:
            notes.append(f"Sharp money moved line down {lm['movement']} — books expect low scoring")

        return notes[:4]

    # ── Dog cover analysis ────────────────────────────────────────────────────

    def _dog_cover_analysis(self, game: dict[str, Any], d: dict[str, Any]) -> dict[str, Any]:
        """Assess probability of dog covering +1.5, winning outright, and margin."""
        dog_score = d.get("dog_score", 0)
        dog_side = d.get("dog_side")
        if not game or not dog_side:
            return {}

        # Cover +1.5 probability band
        if dog_score >= 80:
            cover_pct = "70–80%"
            cover_label = "STRONG +1.5 COVER"
        elif dog_score >= 70:
            cover_pct = "60–70%"
            cover_label = "LIKELY +1.5 COVER"
        elif dog_score >= 60:
            cover_pct = "50–60%"
            cover_label = "+1.5 COVER LEAN"
        else:
            cover_pct = "40–50%"
            cover_label = "MARGINAL COVER"

        # Win outright probability
        if dog_score >= 80:
            win_label = "Outright win in play"
        elif dog_score >= 70:
            win_label = "Outright win possible"
        else:
            win_label = "Needs run line cushion"

        # Win by 2+ (margin > 1.5)
        opp_side = "home" if dog_side == "away" else "away"
        opp_pitcher = (game.get("pitcher_data") or {}).get(opp_side) or {}
        opp_bullpen = (game.get("bullpen_data") or {}).get(opp_side) or {}
        opp_offense = (game.get("offense_data") or {}).get(opp_side) or {}

        margin_notes = []
        if opp_pitcher.get("under_score", 5) >= 7:
            margin_notes.append(f"Fav SP is strong — margin unlikely to be large")
        if (opp_bullpen.get("pct_fatigued") or 0) >= 0.5:
            margin_notes.append("Fav bullpen gassed — dog can pad late")
        if opp_offense.get("streak") == "cold":
            margin_notes.append(f"Fav bats cold — dog limits damage from other side")

        dog_offense = (game.get("offense_data") or {}).get(dog_side) or {}
        if dog_offense.get("streak") == "hot":
            margin_notes.append(f"Dog bats hot — {dog_offense.get('runs_per_game_10d', '?')} rpg L10, win margin realistic")

        dog_pitcher = (game.get("pitcher_data") or {}).get(dog_side) or {}
        if dog_pitcher.get("under_score", 5) >= 7:
            margin_notes.append(f"Dog SP dominant — keeps fav off board, controls margin")

        win_by_margin = dog_score >= 75 and len([n for n in margin_notes if "pad" in n or "hot" in n or "dominant" in n]) >= 1

        return {
            "cover_label": cover_label,
            "cover_pct": cover_pct,
            "win_label": win_label,
            "win_by_margin": win_by_margin,
            "margin_notes": margin_notes[:3],
        }

    # ── helpers ──────────────────────────────────────────────────────────────

    def _under_confidence(self, score: float) -> str:
        if score >= 80: return "STRONG"
        if score >= 70: return "MODERATE"
        if score >= 60: return "LEAN"
        return "PASS"

    def _calc_parlay_odds(self, odds_list: list[float]) -> tuple[str, float]:
        decimal = 1.0
        for o in odds_list:
            d = (o / 100.0) + 1 if o > 0 else (100.0 / abs(o)) + 1
            decimal *= d
        payout = decimal - 1
        if decimal >= 2.0:
            return f"+{round(payout * 100)}", payout
        return f"{round(-100 / payout)}", payout

    def _empty(self) -> dict[str, Any]:
        return {
            "safe_play": None,
            "top_unders": [], "way_under_candidates": [], "top_dogs": [],
            "top_overs": [], "top_faves": [],
            "parlay": {"legs": [], "combined_odds": "—", "payout_per_100": 0, "structure": ""},
            "power_parlay": {"legs": [], "combined_odds": "—", "payout_per_100": 0, "structure": ""},
            "tease_parlay": {"legs": [], "combined_odds": "—", "payout_per_100": 0, "structure": ""},
            "pleaser_parlay": {"legs": [], "combined_odds": "—", "payout_per_100": 0, "structure": ""},
            "out_the_park_parlay": {"legs": [], "combined_odds": "—", "payout_per_100": 0, "structure": ""},
            "way_out_the_park_parlay": {"legs": [], "combined_odds": "—", "payout_per_100": 0, "structure": ""},
            "longshot_parlay": {"legs": [], "combined_odds": "—", "payout_per_100": 0, "structure": ""},
            "rankings": [],
            "watch_list": [],
            "skip_list": [],
            "flagged_lines": [],
            "total_preview_games": 0,
        }
