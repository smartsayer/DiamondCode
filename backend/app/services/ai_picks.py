from typing import Any, Optional
from app.services import pricing


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
        broad_faves = self._rank_faves(clean, min_score=45)
        safe_play = self._identify_safe_play(clean, top_unders)
        parlay = self._build_smart_parlay(safe_play, top_unders, top_dogs, way_unders)
        power_parlay = self._build_power_parlay(top_overs, top_faves, top_unders, top_dogs)
        out_the_park_parlay = self._build_out_the_park_parlay(top_unders, top_dogs, broad_faves)
        # No game exclusion between OTP and WOTP — bets are structurally different
        # (OTP = dogs -1.5 / faves -1.5 / unders -1.5 vs WOTP = faves -2.5 / unders -2.0)
        # so overlapping games are fine; they're completely different bets on the same game.
        way_out_the_park_parlay = self._build_way_out_the_park_parlay(
            top_unders, top_dogs, broad_faves, way_unders
        )
        already_winning_parlay = self._build_already_winning_parlay(top_dogs, top_unders)
        nrfi_parlay = self._build_nrfi_parlay(clean)
        f5_under_parlay = self._build_f5_under_parlay(clean)
        best_edge_parlay = self._build_best_edge_parlay(top_unders, top_dogs, broad_faves)
        sharp_parlay = self._build_sharp_parlay(clean)
        formula_parlay = self._build_formula_parlay(clean, top_unders, broad_faves, top_dogs)
        rankings = self._rank_full_board(preview, flagged_pks)
        watch_list = self._build_watch_list(clean)
        skip_list = self._build_skip_list(clean)

        def _strip(items):
            return [{k: v for k, v in item.items() if k != "_game"} for item in items]

        # ── Edge enrichment: every leg gets fair odds, EV %, and tier ────────
        under_lookup = {u["matchup"]: u for u in top_unders}
        for w in way_unders:
            under_lookup.setdefault(w["matchup"], w)
        dog_lookup = {d["matchup"]: d for d in top_dogs}
        fave_lookup = {f["matchup"]: f for f in broad_faves}

        all_parlays = {
            "parlay": parlay,
            "power_parlay": power_parlay,
            "already_winning_parlay": already_winning_parlay,
            "out_the_park_parlay": out_the_park_parlay,
            "way_out_the_park_parlay": way_out_the_park_parlay,
            "nrfi_parlay": nrfi_parlay,
            "f5_under_parlay": f5_under_parlay,
            # best_edge_parlay builds its own edges — skip re-enrichment
        }
        for _name, p in all_parlays.items():
            if p:
                self._enrich_parlay_edges(p, under_lookup, dog_lookup, fave_lookup)

        # Compute parlay-level edge for best_edge_parlay from its pre-built leg edges
        self._compute_best_edge_parlay_ev(best_edge_parlay)

        return {
            "safe_play": _strip([safe_play])[0] if safe_play else None,
            "top_unders": _strip(top_unders[:5]),
            "way_under_candidates": _strip(way_unders),
            "top_dogs": _strip(top_dogs[:5]),
            "top_overs": _strip(top_overs[:5]),
            "top_faves": _strip(top_faves[:5]),
            "parlay": parlay,
            "power_parlay": power_parlay,
            "already_winning_parlay": already_winning_parlay,
            "out_the_park_parlay": out_the_park_parlay,
            "way_out_the_park_parlay": way_out_the_park_parlay,
            "nrfi_parlay": nrfi_parlay,
            "f5_under_parlay": f5_under_parlay,
            "best_edge_parlay": best_edge_parlay,
            "sharp_parlay": sharp_parlay,
            "formula_parlay": formula_parlay,
            "rankings": rankings,
            "watch_list": watch_list,
            "skip_list": skip_list,
            "flagged_lines": flagged,
            "total_preview_games": len(preview),
        }

    # ── Edge / EV enrichment ─────────────────────────────────────────────────

    def _enrich_parlay_edges(
        self,
        parlay: dict,
        under_lookup: dict,
        dog_lookup: dict,
        fave_lookup: dict,
    ) -> None:
        """
        Walks each leg of a parlay, computes our model's probability for that bet,
        and attaches an `edge` dict (fair_odds, market_odds, edge_pct, tier).
        Also computes a parlay-level edge from the joint model probability.
        """
        legs = parlay.get("legs") or []
        if not legs:
            return

        joint_our_prob = 1.0
        any_priced = False

        for leg in legs:
            t = leg.get("type", "")
            matchup = leg.get("matchup", "")
            market_odds = leg.get("odds")
            our_prob: Optional[float] = None

            # UNDER family (regular, way under, F5, NRFI, OTP, WOTP team-total, etc.)
            if "UNDER" in t or t == "F5_UNDER" or t == "NRFI" or t == "TEAM_TOTAL":
                u = under_lookup.get(matchup)
                if u:
                    base_score = u.get("under_score", 50)
                    p = pricing.under_prob_from_score(base_score)
                    # Penalize moved-line unders (less likely than spot under)
                    if t in ("OTP_UNDER",):
                        p -= 0.08   # -1.5 runs moved
                    elif t in ("WOTP_UNDER",):
                        p -= 0.13   # -2.0 runs moved
                    our_prob = max(0.20, min(0.80, p))
                elif t in ("NRFI", "F5_UNDER", "TEAM_TOTAL"):
                    our_prob = 0.55  # baseline for these niche unders when no score

            # FAVE run-line covers
            elif t in ("OTP_FAV_RL", "WOTP_FAV_RL"):
                f = fave_lookup.get(matchup)
                if f:
                    rl_runs = 1.5 if t == "OTP_FAV_RL" else 2.5
                    our_prob = pricing.fav_cover_prob_from_score(
                        f.get("fav_score", 50), f.get("moneyline"), rl_runs
                    )

            # DOG -1.5 (win outright by 2+)
            elif t in ("OTP_DOG_RL", "WOTP_DOG_RL"):
                d = dog_lookup.get(matchup)
                if d:
                    win_p = pricing.dog_win_prob_from_score(
                        d.get("dog_score", 50), d.get("moneyline")
                    )
                    our_prob = win_p * 0.55   # ~55% of wins are by 2+

            # DOG +1.5 cover (Already Winning)
            elif t == "AW_DOG_RL":
                d = dog_lookup.get(matchup)
                if d:
                    base = pricing.dog_rl_cover_prob_from_ml(d.get("moneyline"))
                    score_adj = (d.get("dog_score", 50) - 50) * 0.0010
                    our_prob = max(0.50, min(0.92, base + score_adj))

            # Straight ML — check FAVE side first, then DOG (both can appear as type ML)
            elif t == "ML":
                f = fave_lookup.get(matchup)
                d = dog_lookup.get(matchup)
                play = (leg.get("play") or "").lower()
                if f and (f.get("fav_team", "").lower() in play):
                    # Fave ML: anchored on market ML, score nudges by ~1-2%
                    base = pricing.american_to_prob(f.get("moneyline")) if f.get("moneyline") else 0.55
                    score_adj = (f.get("fav_score", 50) - 50) * 0.0010
                    our_prob = max(0.45, min(0.85, base + score_adj))
                elif d:
                    our_prob = pricing.dog_win_prob_from_score(
                        d.get("dog_score", 50), d.get("moneyline")
                    )

            # Apply the edge bundle
            if our_prob is not None:
                leg["edge"] = pricing.price_leg(our_prob, market_odds)
                joint_our_prob *= our_prob
                any_priced = True
            else:
                # Unpriced leg: assume market-implied prob (zero edge contribution).
                # This keeps the parlay-level math honest instead of fabricating a CRUSH.
                if market_odds is not None:
                    joint_our_prob *= pricing.american_to_prob(market_odds)
                leg["edge"] = {"tier": "UNPRICED", "edge_pct": None, "color": "#666", "icon": "❓"}

        # ── Parlay-level edge ────────────────────────────────────────────────
        if any_priced:
            combined_str = parlay.get("combined_odds", "")
            try:
                cleaned = str(combined_str).replace("+", "").replace("−", "-")
                combined_int = int(cleaned)
                parlay["parlay_edge"] = pricing.price_leg(joint_our_prob, combined_int)
            except (ValueError, AttributeError, TypeError):
                pass

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

    def _rank_faves(self, games: list[dict[str, Any]], min_score: float = 55) -> list[dict[str, Any]]:
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
            fav_ml = ml.get(f"closing_{fav_side}_ml") or ml.get(f"current_{fav_side}_ml")

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
            if fav_score < min_score:
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

    def _estimate_dog_cover_rl_odds(self, dog_ml: float) -> int:
        """
        Dog at +1.5 RL — they cover if they win outright OR lose by exactly 1.
        Calibrated: +1.5 cover prob ≈ dog ML win prob + 0.20 (the 1-run cushion).
        """
        if dog_ml is None:
            return -140
        dog_prob = self._ml_to_prob(dog_ml)
        cover_prob = min(dog_prob + 0.20, 0.84)
        return self._prob_to_ml(cover_prob)

    # ── Already Winning Parlay (Dogs +1.5 RL + Unders) ───────────────────────

    def _build_already_winning_parlay(
        self,
        top_dogs: list[dict[str, Any]],
        top_unders: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        ALREADY WINNING — you're in a winning position before pitch 1.
          - Dogs at +1.5 RL: lose by 1 OR win outright → still cash
          - Unders at the line: scoring has to happen TO beat you
        4 legs: best 2 dogs + best 2 unders (no game overlap).
        """
        candidates: list[dict[str, Any]] = []

        for d in top_dogs:
            odds = self._estimate_dog_cover_rl_odds(d.get("moneyline"))
            candidates.append({
                "_score": d.get("dog_score", 0),
                "_type_order": 0,
                "type": "AW_DOG_RL",
                "play": f"{d['dog_team']} +1.5 RL",
                "matchup": d["matchup"],
                "odds": odds,
                "difficulty": "Dog covers if they lose by 1 OR win outright",
                "reasoning": " · ".join((d.get("reasons") or [])[:2]) if d.get("reasons") else d.get("verdict", ""),
                "dog_team": d["dog_team"],
                "best_book": d.get("best_book"),
            })

        for u in top_unders:
            total = u.get("closing_total") or u.get("current_total")
            if total is None:
                continue
            candidates.append({
                "_score": u.get("under_score", 0),
                "_type_order": 1,
                "type": "AW_UNDER",
                "play": f"UNDER {total}",
                "matchup": u["matchup"],
                "odds": -110,
                "difficulty": f"Total stays under {total} — scoring works against you",
                "reasoning": " · ".join((u.get("reasons") or [])[:2]) if u.get("reasons") else u.get("verdict", ""),
                "best_book": u.get("best_book"),
            })

        if not candidates:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "structure": "", "note": "No qualifying plays yet — updates as lines come in"}

        # Alternate: pick best dog, best under, second dog, second under
        candidates.sort(key=lambda x: (-x["_type_order"], -x["_score"]))
        dogs = [c for c in candidates if c["type"] == "AW_DOG_RL"]
        unders = [c for c in candidates if c["type"] == "AW_UNDER"]

        legs: list[dict[str, Any]] = []
        used: set[str] = set()
        rank_labels = ("LOCK", "STRONG", "LEAN", "DART")

        # Interleave: dog → under → dog → under for balance
        pools = [dogs, unders, dogs, unders]
        seen_per_pool: list[set] = [set(), set(), set(), set()]
        for pool_idx, pool in enumerate(pools):
            for c in pool:
                if c["matchup"] in used or c["matchup"] in seen_per_pool[pool_idx]:
                    continue
                legs.append(c)
                used.add(c["matchup"])
                seen_per_pool[pool_idx].add(c["matchup"])
                break
            if len(legs) == 4:
                break

        for i, leg in enumerate(legs, start=1):
            leg["rank"] = i
            leg["rank_label"] = rank_labels[i - 1] if i <= len(rank_labels) else "DART"
            leg.pop("_score", None)
            leg.pop("_type_order", None)

        combined_american, payout = self._calc_parlay_odds([l["odds"] for l in legs])

        structure_parts = []
        for l in legs:
            if l["type"] == "AW_DOG_RL":
                structure_parts.append(f"🐕 {l.get('dog_team','').split()[-1]} +1.5")
            else:
                structure_parts.append(f"📉 U{l['play'].split()[-1]}")

        partial = " — more games qualifying as lines post" if len(legs) < 4 else ""
        return {
            "legs": legs,
            "combined_odds": combined_american,
            "payout_per_100": round(payout * 100, 2),
            "structure": " · ".join(structure_parts),
            "note": f"{len(legs)}-leg ALREADY WINNING — you're ahead before the first pitch{partial}",
        }

    # ── Power Parlay (Overs + Favorites) ─────────────────────────────────────

    def _build_power_parlay(
        self,
        overs: list[dict[str, Any]],
        faves: list[dict[str, Any]],
        unders: Optional[list[dict[str, Any]]] = None,
        dogs: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """
        BEST PARLAY OF THE DAY — one top conviction pick from each category,
        no score minimums. Always shows whatever is available.
        Priority order: best under → best dog → best fave → best over.
        """
        legs: list[dict[str, Any]] = []
        used: set[str] = set()

        # Best under
        for u in (unders or []):
            if u["matchup"] not in used:
                leg = self._under_leg(u)
                leg["leg_role"] = "📉 BEST UNDER"
                legs.append(leg)
                used.add(u["matchup"])
                break

        # Best dog (different game from under)
        for d in (dogs or []):
            if d["matchup"] not in used:
                leg = self._dog_leg(d)
                leg["leg_role"] = f"🐕 {d['dog_team'].split()[-1].upper()} DOG"
                legs.append(leg)
                used.add(d["matchup"])
                break

        # Best fave (different game)
        for f in (faves or []):
            if f["matchup"] not in used:
                leg = self._fave_leg(f)
                leg["leg_role"] = f"⭐ {f['fav_team'].split()[-1].upper()} {f.get('play_suggestion', 'ML')}"
                legs.append(leg)
                used.add(f["matchup"])
                break

        # Best over (different game)
        for o in (overs or []):
            if o["matchup"] not in used:
                leg = self._over_leg(o)
                leg["leg_role"] = "📈 BEST OVER"
                legs.append(leg)
                used.add(o["matchup"])
                break

        if not legs:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "note": "No plays available yet — updates as lines come in", "structure": ""}

        combined_american, payout = self._calc_parlay_odds([leg["odds"] for leg in legs])
        partial = " — more legs posting as lines open" if len(legs) < 4 else ""
        return {
            "legs": legs,
            "combined_odds": combined_american,
            "payout_per_100": round(payout * 100, 2),
            "note": f"{len(legs)}-leg BEST PARLAY — highest conviction pick from each category{partial}",
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
        OUT THE PARK — layered tease parlay. Each line moved 1.5 runs against you.
        Locked structure (always the same shape, best of each type):
          Layer A: 2 × FAVE -1.5 RL   (anchors — fav must win by 2+)
          Layer B: 1 × DOG  -1.5 RL   (upset — dog must win outright by 2+)
          Layer C: 1 × UNDER -1.5     (totals — game stays 1.5 below the line)
        Order: FAVE → FAVE → UPSET → UNDER.
        """
        # ── Layer A: Top 2 faves at -1.5 RL ───────────────────────────────────
        fave_legs: list[dict[str, Any]] = []
        used: set[str] = set()
        for f in sorted(top_faves, key=lambda x: x.get("fav_score", 0), reverse=True):
            if f.get("moneyline") is None:
                continue
            if f["matchup"] in used:
                continue
            leg_odds = self._estimate_fav_rl_odds(f.get("moneyline"))
            fave_legs.append({
                "type": "OTP_FAV_RL",
                "play": f"{f['fav_team']} -1.5 RL",
                "matchup": f["matchup"],
                "original_line": "ML",
                "moved_line": "-1.5 (win by 2+)",
                "odds": leg_odds,
                "difficulty": "Favorite must WIN BY 2+ runs",
                "reasoning": " · ".join((f.get("reasons") or [])[:2]) if f.get("reasons") else f.get("verdict", ""),
                "fav_team": f["fav_team"],
                "best_book": f.get("best_book"),
            })
            used.add(f["matchup"])
            if len(fave_legs) >= 2:
                break

        # ── Layer B: Top 1 dog at -1.5 RL (must win by 2+) ────────────────────
        dog_leg: Optional[dict[str, Any]] = None
        for d in sorted(top_dogs, key=lambda x: x.get("dog_score", 0), reverse=True):
            if d.get("moneyline") is None:
                continue
            if d["matchup"] in used:
                continue
            leg_odds = self._estimate_dog_rl_odds(d.get("moneyline"))
            dog_leg = {
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
            }
            used.add(d["matchup"])
            break

        # ── Layer C: Top 1 under at -1.5 below the line ───────────────────────
        under_leg: Optional[dict[str, Any]] = None
        for u in top_unders:
            if u["matchup"] in used:
                continue
            closing = u.get("closing_total")
            if closing is None:
                continue
            moved = round(closing - self._OUT_THE_PARK_AMOUNT, 1)
            if moved < 4.0:
                continue
            leg_odds = self._estimate_moved_under_odds(closing, moved)
            under_leg = {
                "type": "OTP_UNDER",
                "play": f"UNDER {moved}",
                "matchup": u["matchup"],
                "original_line": closing,
                "moved_line": moved,
                "odds": leg_odds,
                "difficulty": f"Game must finish under {moved} (1.5 runs tougher than {closing})",
                "reasoning": " · ".join((u.get("reasons") or [])[:2]) if u.get("reasons") else u.get("verdict", ""),
                "best_book": u.get("best_book"),
            }
            used.add(u["matchup"])
            break

        # ── Assemble in order: FAVE → FAVE → UPSET → UNDER ────────────────────
        legs: list[dict[str, Any]] = []
        legs.extend(fave_legs)
        if dog_leg:
            legs.append(dog_leg)
        if under_leg:
            legs.append(under_leg)

        if not legs:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "structure": "", "note": "Not enough qualifiers yet — updates as lines come in",
                    "otp_amount": f"{self._OUT_THE_PARK_AMOUNT} runs"}

        # Layered rank labels — match WOTP visual language
        _fave_labels = ["FAVE ANCHOR", "FAVE SUPPORT"]
        fave_i = 0
        for i, leg in enumerate(legs, start=1):
            leg["rank"] = i
            if leg["type"] == "OTP_FAV_RL":
                leg["rank_label"] = _fave_labels[fave_i] if fave_i < len(_fave_labels) else "FAVE"
                fave_i += 1
            elif leg["type"] == "OTP_DOG_RL":
                leg["rank_label"] = "UPSET PICK"
            else:
                leg["rank_label"] = "UNDER HAMMER"

        combined_american, payout = self._calc_parlay_odds([l["odds"] for l in legs])

        structure_parts = []
        for l in legs:
            tag = (
                f"⭐ {l.get('fav_team','').split()[-1]} -1.5" if l["type"] == "OTP_FAV_RL"
                else f"🐕 {l.get('dog_team','').split()[-1]} -1.5" if l["type"] == "OTP_DOG_RL"
                else "📉 U-1.5"
            )
            structure_parts.append(f"#{l['rank']} {tag}")

        fave_count = sum(1 for l in legs if l["type"] == "OTP_FAV_RL")
        dog_count  = sum(1 for l in legs if l["type"] == "OTP_DOG_RL")
        under_count = sum(1 for l in legs if l["type"] == "OTP_UNDER")

        return {
            "legs": legs,
            "combined_odds": combined_american,
            "payout_per_100": round(payout * 100, 2),
            "otp_amount": f"{self._OUT_THE_PARK_AMOUNT} runs",
            "structure": " · ".join(structure_parts),
            "note": f"{len(legs)}-leg OUT THE PARK — layered: {fave_count} fave -1.5 · {dog_count} dog upset -1.5 · {under_count} under -1.5",
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
        way_unders: Optional[list[dict[str, Any]]] = None,
        exclude_matchups: Optional[set] = None,
    ) -> dict[str, Any]:
        """
        WAY OUT THE PARK — deliberately layered structure: 2 fave -2.5 RL anchors + 2 way-unders.
        The layering is enforced: fave legs and under legs are selected independently
        from the best of each type, then interleaved [fave, under, fave, under].
        This guarantees the parlay always has 2 different bet types and tells a clear story.
        """
        exclude = exclude_matchups or set()

        # ── Layer A: FAVES at -2.5 RL — pick top 2 by fav_score ──────────────
        fave_legs: list[dict[str, Any]] = []
        used_fave: set[str] = set()
        for f in sorted(top_faves, key=lambda x: x.get("fav_score", 0), reverse=True):
            if f["matchup"] in exclude or f["matchup"] in used_fave:
                continue
            if f.get("moneyline") is None:
                continue
            leg_odds = self._estimate_fav_alt_rl_odds(f.get("moneyline"), self._WOTP_FAV_RUNS)
            fave_legs.append({
                "type": "WOTP_FAV_RL",
                "play": f"{f['fav_team']} -{self._WOTP_FAV_RUNS} RL",
                "matchup": f["matchup"],
                "original_line": "ML",
                "moved_line": f"-{self._WOTP_FAV_RUNS} (win by 3+)",
                "odds": leg_odds,
                "difficulty": "Favorite must WIN BY 3+ runs",
                "reasoning": " · ".join((f.get("reasons") or [])[:2]) if f.get("reasons") else f.get("verdict", ""),
                "fav_team": f["fav_team"],
                "best_book": f.get("best_book"),
                "_score": f.get("fav_score", 0),
            })
            used_fave.add(f["matchup"])
            if len(fave_legs) >= 2:
                break

        # ── Layer B: UNDERS moved -2 runs — pick top 2 by under_score ─────────
        under_legs: list[dict[str, Any]] = []
        used_under: set[str] = set()
        under_sources = list(way_unders or []) + [
            u for u in top_unders if u["matchup"] not in {x["matchup"] for x in (way_unders or [])}
        ]
        for u in under_sources:
            if u["matchup"] in exclude or u["matchup"] in used_under:
                continue
            if u["matchup"] in used_fave:
                continue  # don't double-dip same game
            closing = u.get("closing_total")
            if closing is None:
                continue
            moved = round(closing - self._WOTP_UNDER_RUNS, 1)
            if moved < 4.0:
                continue
            leg_odds = self._estimate_moved_under_odds(closing, moved)
            under_legs.append({
                "type": "WOTP_UNDER",
                "play": f"UNDER {moved}",
                "matchup": u["matchup"],
                "original_line": closing,
                "moved_line": moved,
                "odds": leg_odds,
                "difficulty": f"Game must finish under {moved} ({self._WOTP_UNDER_RUNS} runs tougher than {closing})",
                "reasoning": " · ".join((u.get("reasons") or [])[:2]) if u.get("reasons") else u.get("verdict", ""),
                "best_book": u.get("best_book"),
                "_score": u.get("under_score", 0),
            })
            used_under.add(u["matchup"])
            if len(under_legs) >= 2:
                break

        if not fave_legs and not under_legs:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "structure": "", "note": "Not enough qualifiers yet — updates as lines come in"}

        # ── Interleave: fave → under → fave → under ───────────────────────────
        # Fills whichever layers exist, up to 4 legs total
        legs: list[dict[str, Any]] = []
        fi, ui = 0, 0
        for _ in range(4):
            if fi < len(fave_legs) and (ui >= len(under_legs) or fi <= ui):
                legs.append(fave_legs[fi]); fi += 1
            elif ui < len(under_legs):
                legs.append(under_legs[ui]); ui += 1
            else:
                break

        # Stamp rank labels that reflect the layer role
        _fave_labels = ["FAVE ANCHOR", "FAVE SUPPORT"]
        _under_labels = ["UNDER LOCK", "UNDER HAMMER"]
        fave_rank = under_rank = 0
        for i, leg in enumerate(legs, start=1):
            leg["rank"] = i
            if leg["type"] == "WOTP_FAV_RL":
                leg["rank_label"] = _fave_labels[fave_rank] if fave_rank < len(_fave_labels) else "FAVE"
                fave_rank += 1
            else:
                leg["rank_label"] = _under_labels[under_rank] if under_rank < len(_under_labels) else "UNDER"
                under_rank += 1
            leg.pop("_score", None)

        combined_american, payout = self._calc_parlay_odds([l["odds"] for l in legs])

        structure_parts = []
        for l in legs:
            tag = (
                f"⭐ {l.get('fav_team','').split()[-1]} -2.5" if l["type"] == "WOTP_FAV_RL"
                else "📉 U-2"
            )
            structure_parts.append(f"#{l['rank']} {tag}")

        fave_count = sum(1 for l in legs if l["type"] == "WOTP_FAV_RL")
        under_count = len(legs) - fave_count
        layer_desc = f"{fave_count} Fave -2.5 RL · {under_count} Under -2 runs"

        return {
            "legs": legs,
            "combined_odds": combined_american,
            "payout_per_100": round(payout * 100, 2),
            "wotp_amount": layer_desc,
            "structure": " · ".join(structure_parts),
            "note": f"{len(legs)}-leg WAY OUT THE PARK — layered: {fave_count} favorites win by 3+, {under_count} unders drop 2 full runs.",
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
            lm = g.get("line_movement") or {}
            closing = lm.get("closing_total")
            # Fall back to current live total when no closing line cached yet
            current = lm.get("current_total")
            total = closing if closing is not None else current
            if total is None:
                continue
            line_note = None if closing is not None else "line-subject-to-change"
            recs.append({
                "game_pk": g.get("game_pk"),
                "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                "closing_total": total,
                "line_note": line_note,
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
            dog_ml = ml.get(f"closing_{actual}_ml") or ml.get(f"current_{actual}_ml")

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

    def _compute_best_edge_parlay_ev(self, parlay: dict) -> None:
        """Compute joint parlay EV from pre-built leg edges (skip re-enrichment)."""
        legs = parlay.get("legs") or []
        if not legs:
            return
        joint_prob = 1.0
        any_priced = False
        for leg in legs:
            e = leg.get("edge") or {}
            p = e.get("our_prob")
            if p is not None:
                joint_prob *= p
                any_priced = True
            else:
                mkt = leg.get("odds")
                if mkt is not None:
                    joint_prob *= pricing.american_to_prob(mkt)
        if not any_priced:
            return
        combined_str = parlay.get("combined_odds", "")
        try:
            combined_int = int(str(combined_str).replace("+", "").replace("−", "-"))
            parlay["parlay_edge"] = pricing.price_leg(joint_prob, combined_int)
        except (ValueError, AttributeError, TypeError):
            pass

    def _build_formula_parlay(
        self,
        games: list[dict[str, Any]],
        top_unders: list[dict[str, Any]],
        broad_faves: list[dict[str, Any]],
        top_dogs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        THE FORMULA — self-contained correlated parlay.

        Each qualifying game contributes 2-3 correlated legs:
          • UNDER  — best of {full-game UNDER, F5 UNDER}  (never both;
            books block two correlated unders on one parlay)
          • TEAM CONTROL — Favorite ML OR Dog +1.5 RL (whichever edges
            better)
          • NRFI PAD (optional) — no run in the 1st. Added ONLY when the
            game-total under is chosen; if F5 is the under, NRFI is nested
            inside it (innings 1-5) and books block the combo.

        These aren't independent bets — they're one thesis ("low-scoring,
        tightly-played game"). Every leg is positively correlated: low
        totals mean close games with no blowouts and quiet first innings.
        The book prices them independently. That gap is the edge.
        Up to 4 games.
        """
        under_by_pk = {u.get("game_pk"): u for u in top_unders}
        fave_by_pk = {f.get("game_pk"): f for f in broad_faves}
        dog_by_pk = {d.get("game_pk"): d for d in (top_dogs or [])}

        clusters = []
        for g in games:
            pk = g.get("game_pk")
            f5 = g.get("f5") or {}
            f5_score = f5.get("f5_score", 0)
            f5_line = f5.get("projected_f5_line")
            u = under_by_pk.get(pk)
            f = fave_by_pk.get(pk)
            d = dog_by_pk.get(pk)

            # ── Pick ONE under per game ───────────────────────────────────
            # Books treat full-game UNDER and F5 UNDER as correlated and
            # block them on the same parlay. We keep whichever has the
            # better edge — never both.
            matchup = f"{g.get('away_team')} @ {g.get('home_team')}"
            under_score = (u or {}).get("under_score", 0)
            total = (u or {}).get("closing_total")
            under_options = []
            if u and total is not None and under_score >= 55:
                u_odds = u.get("best_price") or -110
                u_prob = pricing.under_prob_from_score(under_score)
                under_options.append({
                    "play": f"UNDER {total}", "type": "FORMULA_UNDER",
                    "odds": u_odds, "edge": pricing.price_leg(u_prob, u_odds),
                    "our_prob": u_prob, "leg_role": "GAME UNDER",
                    "u_score": under_score,
                })
            if f5_score >= 55:
                f5_odds = -120
                f5_prob = pricing.under_prob_from_score(f5_score)
                under_options.append({
                    "play": f"F5 UNDER {f5_line}" if f5_line else "F5 UNDER",
                    "type": "FORMULA_F5_UNDER", "odds": f5_odds,
                    "edge": pricing.price_leg(f5_prob, f5_odds),
                    "our_prob": f5_prob, "leg_role": "F5 UNDER",
                    "u_score": f5_score,
                })
            if not under_options:
                continue
            under_options.sort(
                key=lambda o: (
                    o["edge"].get("edge_pct") if o["edge"].get("edge_pct") is not None else -999,
                    o["our_prob"],
                ),
                reverse=True,
            )
            under_leg = under_options[0]

            # ── Build candidate "team control" legs ───────────────────────
            control_options = []

            fav_ml = f.get("moneyline") if f else None
            fav_team = f.get("fav_team") if f else None
            fav_score = f.get("fav_score", 0) if f else 0
            if f and fav_ml is not None and fav_team and fav_score >= 50:
                fav_base = pricing.american_to_prob(fav_ml)
                fav_prob = max(0.45, min(0.85, fav_base + (fav_score - 50) * 0.0010))
                fav_edge = pricing.price_leg(fav_prob, fav_ml)
                control_options.append({
                    "play": f"{fav_team} ML", "type": "FORMULA_FAV_ML",
                    "odds": fav_ml, "edge": fav_edge, "our_prob": fav_prob,
                    "leg_role": "FAVORITE ML", "ctrl_score": fav_score,
                })

            dog_ml = d.get("moneyline") if d else None
            dog_team = d.get("dog_team") if d else None
            dog_score = d.get("dog_score", 0) if d else 0
            if d and dog_ml is not None and dog_team and dog_score >= 50:
                base_cover = pricing.dog_rl_cover_prob_from_ml(dog_ml)
                dog_prob = max(0.50, min(0.92, base_cover + (dog_score - 50) * 0.0010))
                # Dog +1.5 is the FAVORED side (negative odds). Fair price from
                # cover prob, then a ~4% vig haircut so we don't over-credit.
                rl_odds = pricing.prob_to_american(min(0.96, base_cover * 1.04))
                dog_edge = pricing.price_leg(dog_prob, rl_odds)
                control_options.append({
                    "play": f"{dog_team} +1.5 RL", "type": "FORMULA_DOG_RL",
                    "odds": rl_odds, "edge": dog_edge, "our_prob": dog_prob,
                    "leg_role": "DOG +1.5", "ctrl_score": dog_score,
                })

            if not control_options:
                continue

            # Pick the better-edge control leg (fall back to higher prob)
            control_options.sort(
                key=lambda o: (
                    o["edge"].get("edge_pct") if o["edge"].get("edge_pct") is not None else -999,
                    o["our_prob"],
                ),
                reverse=True,
            )
            control = control_options[0]

            # Correlation strength — the under leg carries the core thesis
            corr_strength = under_leg["u_score"] * 0.58 + control["ctrl_score"] * 0.42

            legs = [
                {
                    "matchup": matchup, "play": under_leg["play"],
                    "type": under_leg["type"], "odds": under_leg["odds"],
                    "edge": under_leg["edge"], "our_prob": under_leg["our_prob"],
                    "leg_role": under_leg["leg_role"],
                },
                {
                    "matchup": matchup, "play": control["play"],
                    "type": control["type"], "odds": control["odds"],
                    "edge": control["edge"], "our_prob": control["our_prob"],
                    "leg_role": control["leg_role"],
                },
            ]

            # ── NRFI pad — first-inning no-run, correlated with the script ─
            # Only when the chosen under is the FULL-GAME under. If F5 was
            # chosen, NRFI is nested inside it (F5 = innings 1-5) and books
            # block that combo. Game-total + NRFI are different markets =
            # placeable.
            nrfi_prob_pct = (g.get("nrfi") or {}).get("nrfi_probability", 0)
            if under_leg["type"] == "FORMULA_UNDER" and nrfi_prob_pct >= 58:
                nrfi_prob = max(0.50, min(0.80, nrfi_prob_pct / 100.0))
                # No NRFI market in the free feed — fair price from prob
                # with a ~4% vig haircut (standard NRFI juice ≈ -115/-130).
                nrfi_odds = pricing.prob_to_american(min(0.95, nrfi_prob * 1.04))
                legs.append({
                    "matchup": matchup, "play": "NRFI (no run 1st inning)",
                    "type": "FORMULA_NRFI", "odds": nrfi_odds,
                    "edge": pricing.price_leg(nrfi_prob, nrfi_odds),
                    "our_prob": nrfi_prob, "leg_role": "NRFI PAD",
                })

            # Naive (independent) joint probability — what the book prices off
            naive_triple = 1.0
            for _lg in legs:
                naive_triple *= _lg["our_prob"]
            # Correlation-adjusted, HONESTLY bounded. Hard ceiling: the joint
            # can never exceed its least-likely leg. Positive correlation
            # moves the true joint a CONSERVATIVE fraction of the way from
            # independent toward that ceiling. 0.30 = moderate correlation
            # (transparent knob). Keeps the estimate believable instead of
            # fabricating a "CRUSH" the way naive p**k would.
            min_leg = min(_lg["our_prob"] for _lg in legs)
            _CORR_FACTOR = 0.30
            corr_triple = naive_triple + _CORR_FACTOR * (min_leg - naive_triple)

            clusters.append({
                "game_pk": pk,
                "matchup": matchup,
                "legs": legs,
                "corr_strength": round(corr_strength, 1),
                "naive_triple": naive_triple,
                "corr_triple": corr_triple,
                "under_score": round(under_score, 1),
                "f5_score": round(f5_score, 1),
                "ctrl_score": round(control["ctrl_score"], 1),
                "ctrl_role": control["leg_role"],
                "ctrl_team": control["play"].rsplit(" ", 1)[0] if control["type"] == "FORMULA_FAV_ML" else control["play"].replace(" +1.5 RL", ""),
            })

        if not clusters:
            return {
                "legs": [], "games": [], "combined_odds": "—", "payout_per_100": 0,
                "structure": "",
                "note": "No games clear all three filters today (UNDER 55+ · Fav 50+ · F5 55+). "
                        "The Formula only fires when the script lines up — that's the point.",
            }

        clusters.sort(key=lambda c: c["corr_strength"], reverse=True)
        top = clusters[:4]

        # Flatten legs, compute combined book odds
        all_legs = []
        for i, c in enumerate(top, start=1):
            for leg in c["legs"]:
                leg["game_index"] = i
                all_legs.append(leg)

        combined, payout = self._calc_parlay_odds([l["odds"] for l in all_legs])

        # Joint probabilities across all games
        joint_naive = 1.0
        joint_corr = 1.0
        for c in top:
            joint_naive *= c["naive_triple"]
            joint_corr *= c["corr_triple"]

        # Honest framing: we deliberately do NOT headline a parlay-level EV%.
        # Stacking 6+ legs compounds model error — a parlay EV built from
        # per-leg edges is exactly the optimistic mirage books profit from.
        # We surface: (a) per-leg standalone edges, (b) the correlation
        # probability lift per game, (c) the book's implied price. The
        # TRACK tab's CLV is the only honest judge of whether this wins.
        try:
            combined_int = int(str(combined).replace("+", "").replace("−", "-"))
            book_implied_pct = round(pricing.american_to_prob(combined_int) * 100, 2)
        except (ValueError, TypeError):
            book_implied_pct = None

        structure = " + ".join(
            c["ctrl_team"].split()[-1] for c in top
        )

        return {
            "legs": all_legs,
            "games": [
                {
                    "matchup": c["matchup"],
                    "ctrl_team": c["ctrl_team"],
                    "ctrl_role": c["ctrl_role"],
                    "corr_strength": c["corr_strength"],
                    "under_score": c["under_score"],
                    "f5_score": c["f5_score"],
                    "ctrl_score": c["ctrl_score"],
                    "legs": c["legs"],
                    "naive_triple_pct": round(c["naive_triple"] * 100, 1),
                    "corr_triple_pct": round(c["corr_triple"] * 100, 1),
                }
                for c in top
            ],
            "combined_odds": combined,
            "payout_per_100": round(payout * 100, 2),
            "structure": structure,
            "book_implied_pct": book_implied_pct,
            "joint_naive_pct": round(joint_naive * 100, 2),
            "joint_corr_pct": round(joint_corr * 100, 2),
            "note": f"{len(top)}-game correlated stack · {len(all_legs)} legs "
                    f"(under + control, plus an NRFI pad when the game-total "
                    f"under is in play). No parlay-EV headline on purpose: "
                    f"stacking compounds model error. Per-leg edges + "
                    f"correlation lift below; the TRACK tab is the judge.",
        }

    def _build_sharp_parlay(self, games: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Pure follow-the-money parlay. No model overlay — every leg is here
        because the LINE moved sharply on it (sharps already bet that side).

        Trigger thresholds:
          • Total moved ≥0.5 runs from open  → SHARP UNDER (or OVER)
          • ML moved ≥15 cents toward a side → that side is SHARP ML
        """
        candidates: list[dict[str, Any]] = []

        for g in games:
            lm = g.get("line_movement") or {}
            ml = g.get("moneyline_data") or {}
            matchup = f"{g.get('away_team')} @ {g.get('home_team')}"

            # ── Total movement (UNDER if dropped, OVER if rose) ──────────────
            tmv = lm.get("total_movement")
            cur_total = lm.get("current_total") or lm.get("closing_total")
            open_total = lm.get("opening_total")
            if tmv is not None and abs(tmv) >= 0.5 and cur_total is not None:
                side = "UNDER" if tmv < 0 else "OVER"
                candidates.append({
                    "game_pk": g.get("game_pk"),
                    "matchup": matchup,
                    "play": f"{side} {cur_total}",
                    "type": f"SHARP_{side}",
                    "odds": -110,
                    "magnitude": abs(tmv) * 10,   # 1 run = 10 ML cents weight
                    "movement_text": f"{open_total} → {cur_total} (moved {tmv:+.1f})",
                    "reasoning": f"Total dropped {abs(tmv):.1f} runs since open — sharp money on {side.lower()}" if tmv < 0
                                 else f"Total rose {abs(tmv):.1f} runs since open — sharp money on the {side.lower()}",
                })

            # ── ML movement (ML got more expensive = sharp came in on that side) ─
            amv = ml.get("away_ml_movement")
            hmv = ml.get("home_ml_movement")
            cur_aml = ml.get("current_away_ml") or ml.get("closing_away_ml") or ml.get("away_ml")
            cur_hml = ml.get("current_home_ml") or ml.get("closing_home_ml") or ml.get("home_ml")
            open_aml = ml.get("opening_away_ml")
            open_hml = ml.get("opening_home_ml")

            # Away ML got more expensive (number went down → more negative or less positive)
            if amv is not None and amv <= -15 and cur_aml is not None:
                away_team = g.get("away_team", "Away")
                candidates.append({
                    "game_pk": g.get("game_pk"),
                    "matchup": matchup,
                    "play": f"{away_team} ML",
                    "type": "SHARP_ML",
                    "odds": cur_aml,
                    "magnitude": abs(amv),
                    "movement_text": f"{open_aml:+d} → {cur_aml:+d} (moved {amv:+.0f})" if open_aml else f"now {cur_aml:+d}",
                    "reasoning": f"{away_team} ML moved {abs(amv):.0f} cents toward fav — sharp money on the away side",
                })
            if hmv is not None and hmv <= -15 and cur_hml is not None:
                home_team = g.get("home_team", "Home")
                candidates.append({
                    "game_pk": g.get("game_pk"),
                    "matchup": matchup,
                    "play": f"{home_team} ML",
                    "type": "SHARP_ML",
                    "odds": cur_hml,
                    "magnitude": abs(hmv),
                    "movement_text": f"{open_hml:+d} → {cur_hml:+d} (moved {hmv:+.0f})" if open_hml else f"now {cur_hml:+d}",
                    "reasoning": f"{home_team} ML moved {abs(hmv):.0f} cents toward fav — sharp money on the home side",
                })

        if not candidates:
            return {
                "legs": [], "combined_odds": "—", "payout_per_100": 0,
                "structure": "",
                "note": "No sharp movement yet — opening lines are still being snapshotted. Check back as sportsbooks reprice.",
            }

        # Dedupe by game (keep biggest signal per matchup), sort by magnitude
        candidates.sort(key=lambda x: x["magnitude"], reverse=True)
        seen: set = set()
        top: list[dict] = []
        for c in candidates:
            gk = c.get("game_pk")
            if gk in seen:
                continue
            seen.add(gk)
            c["rank"] = len(top) + 1
            c["rank_label"] = "STEAM" if c["magnitude"] >= 15 else "SHARP" if c["magnitude"] >= 8 else "DRIFT"
            top.append(c)
            if len(top) == 4:
                break

        combined, payout = self._calc_parlay_odds([l["odds"] for l in top])
        structure = " · ".join(f"#{l['rank']} {l['play'].split()[0]}" for l in top)

        return {
            "legs": top,
            "combined_odds": combined,
            "payout_per_100": round(payout * 100, 2),
            "structure": structure,
            "note": f"{len(top)}-leg sharp-money stack · pure follow-the-line play · no model overlay",
        }

    def _build_best_edge_parlay(
        self,
        top_unders: list[dict[str, Any]],
        top_dogs: list[dict[str, Any]],
        broad_faves: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Pure signal parlay — scans every bet type across every game and keeps
        only the legs with the highest computed EV (≥3%). No fixed structure.
        The engine picks the 4 best-priced bets on the slate regardless of type.
        """
        candidates: list[dict[str, Any]] = []

        # ── Unders ──────────────────────────────────────────────────────────
        for u in top_unders:
            score = u.get("under_score", 0)
            market = u.get("best_price") or -110
            our_prob = pricing.under_prob_from_score(score)
            e = pricing.price_leg(our_prob, market)
            if e.get("edge_pct") is None or e["edge_pct"] < 0.0:
                continue
            candidates.append({
                "game_pk": u.get("game_pk"),
                "matchup": u.get("matchup"),
                "play": f"UNDER {u.get('closing_total')}",
                "type": "BE_UNDER",
                "odds": market,
                "reasoning": (u.get("reasons") or ["Under edge"])[0],
                "edge": e,
                "_score": e["edge_pct"],
            })

        # ── Fave ML ──────────────────────────────────────────────────────────
        for f in broad_faves:
            ml = f.get("moneyline")
            if ml is None:
                continue
            score = f.get("fav_score", 50)
            base = pricing.american_to_prob(ml)
            our_prob = max(0.45, min(0.85, base + (score - 50) * 0.0010))
            e = pricing.price_leg(our_prob, ml)
            if e.get("edge_pct") is None or e["edge_pct"] < 0.0:
                continue
            candidates.append({
                "game_pk": f.get("game_pk"),
                "matchup": f.get("matchup"),
                "play": f"{f.get('fav_team')} ML",
                "type": "BE_FAV_ML",
                "odds": ml,
                "reasoning": (f.get("reasons") or ["Fave edge"])[0],
                "edge": e,
                "_score": e["edge_pct"],
            })

        # ── Fave -1.5 RL ─────────────────────────────────────────────────────
        for f in broad_faves:
            ml = f.get("moneyline")
            if ml is None:
                continue
            score = f.get("fav_score", 50)
            our_prob = pricing.fav_cover_prob_from_score(score, ml, 1.5)
            rl_odds = self._estimate_fav_rl_odds(ml)
            e = pricing.price_leg(our_prob, rl_odds)
            if e.get("edge_pct") is None or e["edge_pct"] < 0.0:
                continue
            candidates.append({
                "game_pk": f.get("game_pk"),
                "matchup": f.get("matchup"),
                "play": f"{f.get('fav_team')} -1.5 RL",
                "type": "BE_FAV_RL",
                "odds": rl_odds,
                "reasoning": (f.get("reasons") or ["Fave RL edge"])[0],
                "edge": e,
                "_score": e["edge_pct"],
            })

        # ── Dog ML ───────────────────────────────────────────────────────────
        for d in top_dogs:
            ml = d.get("moneyline")
            if ml is None:
                continue
            score = d.get("dog_score", 50)
            our_prob = pricing.dog_win_prob_from_score(score, ml)
            e = pricing.price_leg(our_prob, ml)
            if e.get("edge_pct") is None or e["edge_pct"] < 0.0:
                continue
            candidates.append({
                "game_pk": d.get("game_pk"),
                "matchup": d.get("matchup"),
                "play": f"{d.get('dog_team')} ML UPSET",
                "type": "BE_DOG_ML",
                "odds": ml,
                "reasoning": (d.get("reasons") or ["Dog edge"])[0],
                "edge": e,
                "_score": e["edge_pct"],
            })

        # ── Dog +1.5 RL ──────────────────────────────────────────────────────
        for d in top_dogs:
            ml = d.get("moneyline")
            if ml is None:
                continue
            score = d.get("dog_score", 50)
            base_cover = pricing.dog_rl_cover_prob_from_ml(ml)
            our_prob = max(0.50, min(0.92, base_cover + (score - 50) * 0.0010))
            # +1.5 is the FAVORED side (negative odds). Fair price from the
            # cover prob with a ~4% vig haircut — NOT _estimate_dog_rl_odds,
            # which returns the dog -1.5 (win-by-2) longshot price.
            rl_odds = pricing.prob_to_american(min(0.96, base_cover * 1.04))
            e = pricing.price_leg(our_prob, rl_odds)
            if e.get("edge_pct") is None or e["edge_pct"] < 0.0:
                continue
            candidates.append({
                "game_pk": d.get("game_pk"),
                "matchup": d.get("matchup"),
                "play": f"{d.get('dog_team')} +1.5 RL",
                "type": "BE_DOG_RL",
                "odds": rl_odds,
                "reasoning": (d.get("reasons") or ["Dog +1.5 edge"])[0],
                "edge": e,
                "_score": e["edge_pct"],
            })

        # Sort by edge%, deduplicate by game_pk (best bet per game only), fill to 4
        candidates.sort(key=lambda x: x["_score"], reverse=True)
        seen_games: set = set()
        top: list[dict] = []
        for c in candidates:
            gk = c.get("game_pk")
            if gk in seen_games:
                continue
            seen_games.add(gk)
            top.append(c)
            if len(top) == 4:
                break

        if not top:
            return {
                "legs": [], "combined_odds": "—", "payout_per_100": 0,
                "structure": "", "note": "No EDGE-tier legs today — check back as lines sharpen",
            }

        # Rank labels by edge tier
        tier_labels = {"CRUSH": "💎 CRUSH", "EDGE": "📈 EDGE", "FAIR": "⚖️ FAIR", "PASS": "🚫 PASS"}
        for i, leg in enumerate(top, start=1):
            leg["rank"] = i
            leg["rank_label"] = tier_labels.get(leg["edge"].get("tier", ""), f"#{i}")
            leg.pop("_score", None)

        combined, payout = self._calc_parlay_odds([l["odds"] for l in top])
        structure = " · ".join(f"#{l['rank']} {l['play'].split()[0]}" for l in top)
        evs = [l["edge"].get("edge_pct", 0) or 0 for l in top]
        avg_ev = round(sum(evs) / len(evs), 1)
        best_tier = top[0]["edge"].get("tier", "FAIR") if top else "FAIR"

        return {
            "legs": top,
            "combined_odds": combined,
            "payout_per_100": round(payout * 100, 2),
            "structure": structure,
            "note": f"{len(top)}-leg best-edge stack · avg leg EV {'+' if avg_ev >= 0 else ''}{avg_ev}% · pure signal, no fixed structure",
            "avg_leg_ev": avg_ev,
            "best_tier": best_tier,
        }

    def _empty(self) -> dict[str, Any]:
        empty_parlay = {"legs": [], "combined_odds": "—", "payout_per_100": 0, "structure": ""}
        return {
            "safe_play": None,
            "top_unders": [], "way_under_candidates": [], "top_dogs": [],
            "top_overs": [], "top_faves": [],
            "parlay": empty_parlay,
            "power_parlay": empty_parlay,
            "out_the_park_parlay": empty_parlay,
            "way_out_the_park_parlay": empty_parlay,
            "nrfi_parlay": empty_parlay,
            "f5_under_parlay": empty_parlay,
            "best_edge_parlay": empty_parlay,
            "sharp_parlay": empty_parlay,
            "formula_parlay": empty_parlay,
            "rankings": [],
            "watch_list": [],
            "skip_list": [],
            "flagged_lines": [],
            "total_preview_games": 0,
        }

    # ── NRFI Parlay (No Run First Inning) ────────────────────────────────────

    def _build_nrfi_parlay(self, games: list[dict[str, Any]]) -> dict[str, Any]:
        """4 NRFIs stacked. Each leg ~62-65% to hit. Pays roughly +900-1500."""
        candidates = []
        for g in games:
            nrfi = g.get("nrfi") or {}
            prob = nrfi.get("nrfi_probability", 0)
            if prob < 60:
                continue
            candidates.append({
                "game_pk": g.get("game_pk"),
                "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                "play": "NRFI (No Run 1st Inning)",
                "type": "NRFI",
                "probability": prob,
                "odds": self._prob_to_ml(prob / 100),
                "reasoning": " · ".join(nrfi.get("key_factors", [])[:2]) or nrfi.get("verdict", ""),
            })
        if not candidates:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "structure": "", "note": "No NRFI qualifiers yet — updates as lines come in"}
        candidates.sort(key=lambda x: x["probability"], reverse=True)
        legs = candidates[:4]
        rank_labels = ("LOCK", "STRONG", "LEAN", "DART")
        for i, leg in enumerate(legs, start=1):
            leg["rank"] = i
            leg["rank_label"] = rank_labels[i-1] if i <= len(rank_labels) else "DART"
        combined, payout = self._calc_parlay_odds([l["odds"] for l in legs])
        structure = " · ".join(f"#{l['rank']} 🥚 {l['matchup'].split(' @ ')[1].split()[-1]}" for l in legs)
        partial = " — more games qualifying as odds open" if len(legs) < 4 else ""
        return {
            "legs": legs,
            "combined_odds": combined,
            "payout_per_100": round(payout * 100, 2),
            "structure": structure,
            "note": f"{len(legs)}-leg NRFI stack — both starters hold scoreless 1st inning{partial}",
        }

    # ── F5 Under Parlay (First 5 innings) ────────────────────────────────────

    def _build_f5_under_parlay(self, games: list[dict[str, Any]]) -> dict[str, Any]:
        """First-5-inning unders — no bullpen risk, only starter quality matters. Pays ~+800-2000."""
        candidates = []
        for g in games:
            f5 = g.get("f5") or {}
            score = f5.get("f5_score", 0)
            if score < 55:
                continue
            projected = f5.get("projected_f5_line")
            line_str = f"F5 UNDER {projected}" if projected else "F5 UNDER (line TBD)"
            candidates.append({
                "game_pk": g.get("game_pk"),
                "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                "play": line_str,
                "type": "F5_UNDER",
                "f5_score": score,
                "verdict": f5.get("verdict"),
                "odds": -120,
                "reasoning": f"F5 score {score:.0f} — strong starter quality, no pen variance",
            })
        if not candidates:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "structure": "", "note": "No F5 qualifiers yet — updates as starting lineups post"}
        candidates.sort(key=lambda x: x["f5_score"], reverse=True)
        legs = candidates[:4]
        rank_labels = ("LOCK", "STRONG", "LEAN", "DART")
        for i, leg in enumerate(legs, start=1):
            leg["rank"] = i
            leg["rank_label"] = rank_labels[i-1] if i <= len(rank_labels) else "DART"
        combined, payout = self._calc_parlay_odds([l["odds"] for l in legs])
        structure = " · ".join(f"#{l['rank']} 5️⃣U {l['matchup'].split(' @ ')[1].split()[-1]}" for l in legs)
        partial = " — more games qualifying as lineups post" if len(legs) < 4 else ""
        return {
            "legs": legs,
            "combined_odds": combined,
            "payout_per_100": round(payout * 100, 2),
            "structure": structure,
            "note": f"{len(legs)}-leg F5 UNDER stack — no bullpen risk, just elite starters{partial}",
        }

    # ── Team Total Parlay ────────────────────────────────────────────────────

    def _build_team_total_parlay(self, games: list[dict[str, Any]]) -> dict[str, Any]:
        """Stack team unders/overs. Each team total leg is independent variance — high payout."""
        candidates = []
        for g in games:
            tt = g.get("team_totals") or {}
            best_score = tt.get("best_score", 0)
            if best_score < 60:
                continue
            best_team = tt.get("best_team", "")
            verdict = tt.get("best_verdict", "")
            projected = tt.get("best_projected_total")
            line_str = f"{best_team} UNDER {projected}" if projected else f"{best_team} TT UNDER"
            candidates.append({
                "game_pk": g.get("game_pk"),
                "matchup": f"{g.get('away_team')} @ {g.get('home_team')}",
                "play": line_str,
                "type": "TEAM_TOTAL_UNDER",
                "tt_score": best_score,
                "verdict": verdict,
                "team": best_team,
                "odds": -115,
                "reasoning": f"Team-total under {best_score:.0f} — {verdict}",
            })
        if not candidates:
            return {"legs": [], "combined_odds": "—", "payout_per_100": 0,
                    "structure": "", "note": "No team-total qualifiers yet — updates as team totals post"}
        candidates.sort(key=lambda x: x["tt_score"], reverse=True)
        legs = candidates[:4]
        rank_labels = ("LOCK", "STRONG", "LEAN", "DART")
        for i, leg in enumerate(legs, start=1):
            leg["rank"] = i
            leg["rank_label"] = rank_labels[i-1] if i <= len(rank_labels) else "DART"
        combined, payout = self._calc_parlay_odds([l["odds"] for l in legs])
        structure = " · ".join(f"#{l['rank']} 🎯 {l['team'].split()[-1]} U" for l in legs)
        partial = " — more games qualifying as team totals post" if len(legs) < 4 else ""
        return {
            "legs": legs,
            "combined_odds": combined,
            "payout_per_100": round(payout * 100, 2),
            "structure": structure,
            "note": f"{len(legs)}-leg TEAM TOTAL stack — each team's individual scoring capped{partial}",
        }
