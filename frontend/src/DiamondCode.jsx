import { useState, useEffect, createContext, useContext, useCallback, useMemo } from "react";

// ── Bet Slip context — shared state for click-to-add betting ──────────────────
const BetSlipContext = createContext(null);

const SLIP_STORAGE_KEY = "diamondcode_betslip_v1";
const WAGER_STORAGE_KEY = "diamondcode_wager_v1";

function legKey(leg) {
  return `${leg.matchup || ""}|${leg.play || ""}|${leg.type || ""}`;
}

function BetSlipProvider({ children }) {
  const [slip, setSlip] = useState(() => {
    try {
      const raw = localStorage.getItem(SLIP_STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch { return []; }
  });
  const [wager, setWager] = useState(() => {
    try { return localStorage.getItem(WAGER_STORAGE_KEY) || "100"; }
    catch { return "100"; }
  });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [flashId, setFlashId] = useState(null);

  useEffect(() => {
    try { localStorage.setItem(SLIP_STORAGE_KEY, JSON.stringify(slip)); } catch {}
  }, [slip]);
  useEffect(() => {
    try { localStorage.setItem(WAGER_STORAGE_KEY, wager); } catch {}
  }, [wager]);

  const addLeg = useCallback((leg) => {
    if (!leg || leg.odds == null) return;
    const key = legKey(leg);
    setSlip(prev => {
      if (prev.some(l => legKey(l) === key)) return prev;  // dedupe
      const newLeg = {
        id: `leg_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
        matchup: leg.matchup || "",
        play: leg.play || "",
        odds: typeof leg.odds === "number" ? leg.odds : parseInt(leg.odds, 10),
        type: leg.type || "",
        source: leg.source || "",
        edge: leg.edge ? { tier: leg.edge.tier, edge_pct: leg.edge.edge_pct, color: leg.edge.color, icon: leg.edge.icon } : null,
      };
      return [...prev, newLeg];
    });
    setFlashId(key);
    setTimeout(() => setFlashId(null), 700);
  }, []);

  const removeLeg = useCallback((id) => {
    setSlip(prev => prev.filter(l => l.id !== id));
  }, []);

  const removeByKey = useCallback((key) => {
    setSlip(prev => prev.filter(l => legKey(l) !== key));
  }, []);

  const clearSlip = useCallback(() => setSlip([]), []);
  const toggleLeg = useCallback((leg) => {
    const key = legKey(leg);
    setSlip(prev => {
      if (prev.some(l => legKey(l) === key)) {
        return prev.filter(l => legKey(l) !== key);
      }
      // add
      const newLeg = {
        id: `leg_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
        matchup: leg.matchup || "",
        play: leg.play || "",
        odds: typeof leg.odds === "number" ? leg.odds : parseInt(leg.odds, 10),
        type: leg.type || "",
        source: leg.source || "",
        edge: leg.edge ? { tier: leg.edge.tier, edge_pct: leg.edge.edge_pct, color: leg.edge.color, icon: leg.edge.icon } : null,
      };
      setFlashId(key);
      setTimeout(() => setFlashId(null), 700);
      return [...prev, newLeg];
    });
  }, []);

  const isInSlip = useCallback((leg) => {
    if (!leg) return false;
    return slip.some(l => legKey(l) === legKey(leg));
  }, [slip]);

  const value = useMemo(() => ({
    slip, wager, setWager, drawerOpen, setDrawerOpen,
    addLeg, removeLeg, removeByKey, clearSlip, toggleLeg, isInSlip, flashId,
  }), [slip, wager, drawerOpen, addLeg, removeLeg, removeByKey, clearSlip, toggleLeg, isInSlip, flashId]);

  return <BetSlipContext.Provider value={value}>{children}</BetSlipContext.Provider>;
}

function useBetSlip() {
  const ctx = useContext(BetSlipContext);
  if (!ctx) return { slip: [], addLeg: () => {}, removeLeg: () => {}, clearSlip: () => {}, toggleLeg: () => {}, isInSlip: () => false, drawerOpen: false, setDrawerOpen: () => {}, wager: "100", setWager: () => {}, flashId: null };
  return ctx;
}

// ── Placed-bet tracker (auto-saves to localStorage, manual W/L mark) ─────────
const PLACED_KEY = "diamondcode_placed_v1";

function loadPlaced() {
  try { return JSON.parse(localStorage.getItem(PLACED_KEY) || "[]"); }
  catch { return []; }
}

function savePlaced(list) {
  try { localStorage.setItem(PLACED_KEY, JSON.stringify(list)); } catch {}
}

// Trigger a custom event so all subscribers re-read
function emitPlacedChange() {
  window.dispatchEvent(new CustomEvent("diamondcode_placed_changed"));
}

function usePlaced() {
  const [placed, setPlaced] = useState(loadPlaced);
  useEffect(() => {
    const reload = () => setPlaced(loadPlaced());
    window.addEventListener("diamondcode_placed_changed", reload);
    return () => window.removeEventListener("diamondcode_placed_changed", reload);
  }, []);
  const placeBet = (legs, wager) => {
    if (!legs.length) return;
    const list = loadPlaced();
    list.unshift({
      id: `bet_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      placedAt: new Date().toISOString(),
      legs: legs.map(l => ({ ...l })),
      wager: parseFloat(wager) || 0,
      status: "PENDING",   // PENDING | WON | LOST | PUSH
    });
    savePlaced(list);
    emitPlacedChange();
  };
  const updateStatus = (id, status) => {
    const list = loadPlaced().map(b => b.id === id ? { ...b, status, settledAt: new Date().toISOString() } : b);
    savePlaced(list);
    emitPlacedChange();
  };
  const removePlaced = (id) => {
    savePlaced(loadPlaced().filter(b => b.id !== id));
    emitPlacedChange();
  };
  const clearAllPlaced = () => { savePlaced([]); emitPlacedChange(); };

  // Durably capture the closing line for each leg so CLV survives after
  // the game falls off the slate. Only writes once per leg.
  const captureClosings = (games) => {
    if (!games || !games.length) return;
    const byMatchup = {};
    for (const g of games) {
      byMatchup[`${g.away_team} @ ${g.home_team}`] = g;
    }
    let changed = false;
    const list = loadPlaced().map(bet => {
      const legs = bet.legs.map(leg => {
        if (leg.closing != null) return leg;          // already captured
        const g = byMatchup[leg.matchup];
        if (!g) return leg;
        // Only trust the close once the line is locked (game Live/Final)
        const locked = g.abstract_state === "Live" || g.abstract_state === "Final";
        if (!locked) return leg;
        const lm = g.line_movement || {};
        const ml = g.moneyline_data || {};
        let closing = null;
        if (leg.type === "UNDER" || leg.type === "OVER" || leg.type?.includes("UNDER") || leg.type?.includes("OVER")) {
          closing = { total: lm.closing_total ?? lm.current_total ?? null };
        } else if (leg.type === "ML") {
          // Match team in play string to away/home
          const play = (leg.play || "").toLowerCase();
          const awayHit = (g.away_team || "").toLowerCase().split(" ").some(w => w && play.includes(w));
          const aml = ml.closing_away_ml ?? ml.away_ml;
          const hml = ml.closing_home_ml ?? ml.home_ml;
          closing = { ml: awayHit ? aml : hml };
        }
        if (closing && (closing.total != null || closing.ml != null)) {
          changed = true;
          return { ...leg, closing };
        }
        return leg;
      });
      return { ...bet, legs };
    });
    if (changed) { savePlaced(list); emitPlacedChange(); }
  };

  return { placed, placeBet, updateStatus, removePlaced, clearAllPlaced, captureClosings };
}

// CLV for one leg given the price taken and the closing line.
// Returns { pct, beat, label } or null if not computable.
function legCLV(leg) {
  const c = leg.closing;
  if (!c) return null;
  const amToImplied = (am) => am >= 0 ? 100 / (am + 100) : Math.abs(am) / (Math.abs(am) + 100);

  // Totals: parse number from play "UNDER 7.5" / "OVER 7"
  if (leg.type?.includes("UNDER") || leg.type?.includes("OVER")) {
    if (c.total == null) return null;
    const m = String(leg.play).match(/([\d.]+)/);
    if (!m) return null;
    const took = parseFloat(m[1]);
    const close = c.total;
    const isUnder = leg.type.includes("UNDER");
    // UNDER: higher number = better. OVER: lower number = better.
    const diff = isUnder ? (took - close) : (close - took);
    const beat = diff > 0;
    return {
      pct: null,
      beat: diff === 0 ? null : beat,
      label: diff === 0 ? `= ${close} (no move)` : `${leg.play} vs close ${close} (${beat ? "+" : ""}${diff.toFixed(1)} ${beat ? "ahead" : "behind"})`,
    };
  }

  // Moneyline: better price = lower implied prob
  if (leg.type === "ML" && c.ml != null) {
    const took = typeof leg.odds === "number" ? leg.odds : parseInt(leg.odds, 10);
    if (isNaN(took)) return null;
    const yoursImp = amToImplied(took);
    const closeImp = amToImplied(c.ml);
    const clv = (closeImp - yoursImp) * 100;   // positive = you beat the close
    return {
      pct: clv,
      beat: Math.abs(clv) < 0.05 ? null : clv > 0,
      label: `${took >= 0 ? "+" : ""}${took} vs close ${c.ml >= 0 ? "+" : ""}${c.ml}`,
    };
  }
  return null;
}

// Compute parlay decimal odds (and resulting payout) from leg list
function parlayOdds(legs) {
  return legs.reduce((acc, l) => {
    const o = typeof l.odds === "number" ? l.odds : parseInt(l.odds, 10);
    if (isNaN(o)) return acc;
    return acc * (o >= 0 ? 1 + o / 100 : 1 + 100 / Math.abs(o));
  }, 1);
}

// Add-to-slip pill button used inside every leg renderer
function AddPill({ leg, source, accentColor = "#00ff87" }) {
  const { toggleLeg, isInSlip } = useBetSlip();
  const inSlip = isInSlip(leg);
  if (leg?.odds == null) return null;
  const handleClick = (e) => {
    e.stopPropagation();
    toggleLeg({ ...leg, source });
  };
  return (
    <button onClick={handleClick} title={inSlip ? "Remove from bet slip" : "Add to bet slip"} style={{
      background: inSlip ? accentColor : `${accentColor}18`,
      border: `1px solid ${inSlip ? accentColor : accentColor + "60"}`,
      color: inSlip ? "#000" : accentColor,
      fontSize: 9, fontWeight: 800, fontFamily: "monospace",
      padding: "2px 8px", borderRadius: 12, cursor: "pointer",
      letterSpacing: 1, lineHeight: 1.4,
      boxShadow: inSlip ? `0 0 6px ${accentColor}80` : "none",
      transition: "all 0.15s",
    }}>
      {inSlip ? "✓ ON SLIP" : "+ ADD"}
    </button>
  );
}

const VERDICT_CONFIG = {
  Lock:     { label: "🔒 LOCK IT",     color: "#00ff87" },
  Strong:   { label: "✅ STRONG LEAN", color: "#ffd700" },
  Moderate: { label: "⚠️ MODERATE",    color: "#ff9500" },
  Skip:     { label: "❌ SKIP",         color: "#ff3b3b" },
};

const DOG_CONFIG = {
  "Strong Dog": { color: "#a78bfa" },
  "Lean Dog":   { color: "#c4b5fd" },
  "Watch":      { color: "#6b7280" },
  "Fade":       { color: "#374151" },
};

function ScoreGauge({ score, size = "lg", color }) {
  const auto = score >= 80 ? "#00ff87" : score >= 65 ? "#ffd700" : score >= 50 ? "#ff9500" : "#ff3b3b";
  const c = color || auto;
  const label = score >= 80 ? "LOCK" : score >= 65 ? "STRONG" : score >= 50 ? "MOD" : "SKIP";
  const dim = size === "lg" ? 110 : 72;
  const fs = size === "lg" ? 28 : 18;
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{
        width: dim, height: dim, borderRadius: "50%",
        border: `3px solid ${c}`,
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        background: `radial-gradient(circle, ${c}15 0%, transparent 70%)`,
        boxShadow: `0 0 20px ${c}35`,
        margin: "0 auto", transition: "all 0.4s ease",
      }}>
        <span style={{ fontSize: fs, fontWeight: 900, color: c, fontFamily: "monospace", lineHeight: 1 }}>
          {score != null ? Math.round(score) : "--"}
        </span>
        {size === "lg" && (
          <span style={{ fontSize: 8, color: c, letterSpacing: 2, fontFamily: "monospace", marginTop: 2 }}>{label}</span>
        )}
      </div>
    </div>
  );
}

function VariableBar({ label, score, weight, note }) {
  const s = score ?? 5;
  const color = s >= 7 ? "#00ff87" : s >= 5 ? "#ffd700" : "#ff3b3b";
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
        <span style={{ fontSize: 10, color: "#666", letterSpacing: 1, textTransform: "uppercase", fontFamily: "monospace" }}>{label}</span>
        <span style={{ fontSize: 10, color, fontFamily: "monospace" }}>{s.toFixed(1)}/10{weight ? ` · ${weight}%` : ""}</span>
      </div>
      <div style={{ background: "#1a1a1a", borderRadius: 2, height: 4, overflow: "hidden" }}>
        <div style={{ width: `${(s / 10) * 100}%`, height: "100%", background: color, transition: "width 0.5s ease" }} />
      </div>
      {note && <div style={{ fontSize: 9, color: "#444", marginTop: 2, fontFamily: "monospace" }}>{note}</div>}
    </div>
  );
}

function Badge({ text, color }) {
  return (
    <span style={{
      background: color + "20", border: `1px solid ${color}50`,
      color, fontSize: 9, fontFamily: "monospace", letterSpacing: 1,
      padding: "2px 7px", borderRadius: 3, textTransform: "uppercase",
    }}>{text}</span>
  );
}

// Edge chip — visible on every priced leg: tier (CRUSH/EDGE/FAIR/PASS) + EV%
function EdgeChip({ edge, size = "sm" }) {
  if (!edge || edge.tier === "UNPRICED") return null;
  const fs = size === "lg" ? 11 : 9;
  const pad = size === "lg" ? "3px 9px" : "2px 6px";
  const pct = edge.edge_pct;
  return (
    <span style={{
      background: edge.color + "20",
      border: `1px solid ${edge.color}70`,
      color: edge.color,
      fontSize: fs, fontFamily: "monospace", letterSpacing: 1,
      padding: pad, borderRadius: 3, fontWeight: 700,
      whiteSpace: "nowrap",
    }} title={`Our prob ${(edge.our_prob*100).toFixed(1)}% · Fair odds ${edge.our_fair_odds > 0 ? '+' : ''}${edge.our_fair_odds}`}>
      {edge.icon} {edge.tier}{pct != null ? ` ${pct > 0 ? '+' : ''}${pct}%` : ''}
    </span>
  );
}

function OddsChip({ label, value, color = "#888", subtitle }) {
  return (
    <div style={{
      background: color + "10", border: `1px solid ${color}25`,
      padding: "4px 10px", borderRadius: 4,
      display: "inline-flex", flexDirection: "column",
      minWidth: 0,
    }}>
      <span style={{ fontSize: 7, color: color, letterSpacing: 1.5, fontFamily: "monospace", fontWeight: 700 }}>
        {label}
      </span>
      <span style={{ fontSize: 12, color: "#fff", fontFamily: "monospace", fontWeight: 700, marginTop: 1 }}>
        {value ?? "—"}
      </span>
      {subtitle && (
        <span style={{ fontSize: 8, color: "#555", fontFamily: "monospace", marginTop: 1 }}>
          {subtitle}
        </span>
      )}
    </div>
  );
}

function OddsRow({ line, moneyline, awayTeam, homeTeam }) {
  if (!line?.has_data) return null;
  const movement = line.movement || 0;
  const moveColor = movement <= -0.5 ? "#00ff87" : movement >= 0.5 ? "#ff3b3b" : "#666";
  const arrow = movement < 0 ? "▼" : movement > 0 ? "▲" : "—";
  const isLive = line.live_total != null && line.live_total !== line.closing_total;

  const awayAbbr = awayTeam?.split(" ").pop() ?? "AWAY";
  const homeAbbr = homeTeam?.split(" ").pop() ?? "HOME";

  return (
    <div style={{ marginTop: 10, marginBottom: 12 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "stretch" }}>
        <OddsChip
          label="CLOSING"
          value={line.closing_total != null ? `O/U ${line.closing_total}` : null}
          subtitle={line.closing_book}
          color="#60a5fa"
        />
        {isLive && (
          <OddsChip
            label="LIVE"
            value={`O/U ${line.live_total}`}
            subtitle={`${arrow} ${Math.abs(movement).toFixed(1)}`}
            color={moveColor}
          />
        )}
        {moneyline?.closing_away_ml != null && (
          <OddsChip
            label={`${awayAbbr} ML CLOSE`}
            value={moneyline.closing_away_ml > 0 ? `+${moneyline.closing_away_ml}` : moneyline.closing_away_ml}
            subtitle={moneyline.book}
            color="#a78bfa"
          />
        )}
        {moneyline?.closing_home_ml != null && (
          <OddsChip
            label={`${homeAbbr} ML CLOSE`}
            value={moneyline.closing_home_ml > 0 ? `+${moneyline.closing_home_ml}` : moneyline.closing_home_ml}
            subtitle={moneyline.book}
            color="#a78bfa"
          />
        )}
        {moneyline?.live_away_ml != null && moneyline?.live_away_ml !== moneyline?.closing_away_ml && (
          <OddsChip
            label={`${awayAbbr} ML LIVE`}
            value={moneyline.live_away_ml > 0 ? `+${moneyline.live_away_ml}` : moneyline.live_away_ml}
            color="#fbbf24"
          />
        )}
        {moneyline?.live_home_ml != null && moneyline?.live_home_ml !== moneyline?.closing_home_ml && (
          <OddsChip
            label={`${homeAbbr} ML LIVE`}
            value={moneyline.live_home_ml > 0 ? `+${moneyline.live_home_ml}` : moneyline.live_home_ml}
            color="#fbbf24"
          />
        )}
      </div>
      {line.signal && line.signal !== "Neutral" && (
        <div style={{ fontSize: 9, color: moveColor, fontFamily: "monospace", marginTop: 6, letterSpacing: 1 }}>
          {line.signal}
        </div>
      )}
    </div>
  );
}

function LiveScoreBanner({ game }) {
  const state = game.abstract_state;
  const live = game.live_score || {};
  if (state !== "Live" && state !== "Final") return null;

  const half = (live.inning_half || "").toLowerCase().startsWith("t") ? "▲ Top" :
               (live.inning_half || "").toLowerCase().startsWith("b") ? "▼ Bot" :
               (live.inning_half || "Mid");

  const awayAbbr = game.away_team_abbr || game.away_team?.split(" ").pop() || "AWAY";
  const homeAbbr = game.home_team_abbr || game.home_team?.split(" ").pop() || "HOME";
  const total = (live.away_runs ?? 0) + (live.home_runs ?? 0);

  const stateColor = state === "Live" ? "#fbbf24" : "#888";
  const stateLabel = state === "Live" ? "● LIVE" : "FINAL";

  return (
    <div style={{
      background: state === "Live" ? "#fbbf2415" : "#1a1a1a",
      borderBottom: `1px solid ${stateColor}40`,
      padding: "10px 18px",
      display: "flex", alignItems: "center", justifyContent: "space-between",
      gap: 12,
    }}>
      <span style={{
        color: stateColor, fontSize: 10, fontFamily: "monospace",
        letterSpacing: 2, fontWeight: 900,
      }}>
        {stateLabel}
        {state === "Live" && live.inning && (
          <span style={{ color: "#aaa", marginLeft: 8, fontWeight: 400 }}>
            {half} {live.inning}
            {live.outs != null && <span style={{ color: "#666" }}> · {live.outs} out</span>}
          </span>
        )}
      </span>
      <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
        <span style={{ fontSize: 13, fontFamily: "monospace", color: "#fff", fontWeight: 700 }}>
          {awayAbbr} <span style={{ color: "#fbbf24", marginLeft: 4 }}>{live.away_runs ?? 0}</span>
          <span style={{ color: "#333", margin: "0 8px" }}>—</span>
          <span style={{ color: "#fbbf24" }}>{live.home_runs ?? 0}</span> {homeAbbr}
        </span>
        <span style={{ fontSize: 9, color: "#666", fontFamily: "monospace" }}>
          {total} R
        </span>
      </div>
    </div>
  );
}

function GameCard({ game }) {
  const [expanded, setExpanded] = useState(false);
  const verdict = game.verdict || "Skip";
  const cfg = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.Skip;
  const score = game.total_score ?? 0;
  const correlation = game.correlation || {};
  const dog = game.dog_score || {};
  const line = game.line_movement || {};
  const fatigue = game.fatigue_data || {};

  const gameTime = game.game_time_utc
    ? new Date(game.game_time_utc).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : null;

  const awayP = game.pitcher_data?.away;
  const homeP = game.pitcher_data?.home;
  const pitcherNote = [
    awayP?.name !== "TBD" ? `${awayP?.name} (${awayP?.era ?? "--"} ERA)` : "Away TBD",
    homeP?.name !== "TBD" ? `${homeP?.name} (${homeP?.era ?? "--"} ERA)` : "Home TBD",
  ].join(" vs ");

  const weatherNote = game.weather_data
    ? `${game.weather_data.temp_f ?? "--"}°F · ${game.weather_data.wind_mph ?? "--"} mph · ${game.weather_data.conditions ?? ""}`
    : null;

  const awayFatigue = fatigue.away;
  const homeFatigue = fatigue.home;
  const fatigueNote = [
    awayFatigue ? `Away: ${awayFatigue.rest_days}d rest${awayFatigue.consecutive_road_games > 2 ? `, ${awayFatigue.consecutive_road_games} road` : ""}` : null,
    homeFatigue ? `Home: ${homeFatigue.rest_days}d rest` : null,
  ].filter(Boolean).join(" · ");

  const bullpenNote = game.bullpen_data
    ? `Away ${Math.round((game.bullpen_data.away?.pct_fatigued ?? 0) * 100)}% tired · Home ${Math.round((game.bullpen_data.home?.pct_fatigued ?? 0) * 100)}% tired`
    : null;

  const seriesLabel = game.series_game_number
    ? `G${game.series_game_number} of ${game.games_in_series}`
    : null;

  const homeDogScore = dog.home_dog_score ?? 0;
  const awayDogScore = dog.away_dog_score ?? 0;
  const bestDog = correlation.best_dog_side === "home"
    ? { score: homeDogScore, verdict: dog.home_dog_verdict, team: game.home_team }
    : { score: awayDogScore, verdict: dog.away_dog_verdict, team: game.away_team };

  const dogColor = DOG_CONFIG[bestDog.verdict]?.color || "#6b7280";

  return (
    <div style={{
      background: "#0a0a0a",
      border: `1px solid ${correlation.is_double_lock ? "#a78bfa" : score >= 65 ? "#1e3a1e" : "#1a1a1a"}`,
      borderRadius: 8, marginBottom: 14, overflow: "hidden",
      boxShadow: correlation.is_double_lock ? "0 0 28px #a78bfa25" : score >= 65 ? `0 0 16px ${cfg.color}10` : "none",
    }}>
      {/* Double lock banner */}
      {correlation.is_double_lock && (
        <div style={{
          background: "linear-gradient(90deg, #7c3aed20, #a78bfa20)",
          borderBottom: "1px solid #a78bfa40",
          padding: "6px 18px", fontSize: 10, color: "#a78bfa",
          fontFamily: "monospace", letterSpacing: 2, textAlign: "center",
        }}>
          🔥 DOUBLE LOCK — UNDER + DOG ALIGNED
        </div>
      )}

      {/* Live score / Final banner */}
      <LiveScoreBanner game={game} />

      {/* Pace note for in-progress games */}
      {game.abstract_state === "Live" && (game.live_under?.pace_note || game.live_dog?.pace_note) && (
        <div style={{
          padding: "8px 18px", background: "#0d0d0d",
          borderBottom: "1px solid #1a1a1a",
          display: "flex", gap: 16, flexWrap: "wrap",
          fontSize: 9, fontFamily: "monospace", letterSpacing: 1,
        }}>
          {game.live_under?.pace_note && (
            <span style={{ color: "#fbbf24" }}>UNDER PACE: <span style={{ color: "#fff" }}>{game.live_under.pace_note}</span></span>
          )}
          {game.live_dog?.pace_note && (
            <span style={{ color: "#a78bfa" }}>DOG: <span style={{ color: "#fff" }}>{game.live_dog.pace_note}</span></span>
          )}
        </div>
      )}

      <div style={{ padding: "18px 20px" }}>
        {/* Header row */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, color: "#fff", fontFamily: "monospace", fontWeight: 700, marginBottom: 5 }}>
              {game.away_team} <span style={{ color: "#333" }}>@</span> {game.home_team}
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 4 }}>
              {gameTime && <Badge text={gameTime} color="#555" />}
              {seriesLabel && <Badge text={seriesLabel} color={game.series_game_number === 1 ? "#00ff87" : "#555"} />}
            </div>
            {game.umpire_data?.umpire_name && game.umpire_data.umpire_name !== "Unknown" && (
              <div style={{ fontSize: 9, color: "#444", fontFamily: "monospace" }}>
                HP: {game.umpire_data.umpire_name}
              </div>
            )}
          </div>

          {/* Score gauges — closing fixed, live changes */}
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 8, color: "#60a5fa", letterSpacing: 1, fontFamily: "monospace", marginBottom: 4 }}>CLOSE UNDER</div>
              <ScoreGauge score={Math.round(score)} size="lg" />
              {game.live_under?.live_under_score != null && (
                <div style={{ marginTop: 6 }}>
                  <div style={{ fontSize: 7, color: "#fbbf24", letterSpacing: 1.5 }}>LIVE</div>
                  <div style={{ fontSize: 13, color: "#fbbf24", fontFamily: "monospace", fontWeight: 700 }}>
                    {Math.round(game.live_under.live_under_score)}
                    {game.live_under.delta !== 0 && (
                      <span style={{ fontSize: 9, marginLeft: 4, color: game.live_under.delta > 0 ? "#00ff87" : "#ff3b3b" }}>
                        {game.live_under.delta > 0 ? "▲" : "▼"}{Math.abs(game.live_under.delta)}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 8, color: "#a78bfa", letterSpacing: 1, fontFamily: "monospace", marginBottom: 4 }}>CLOSE DOG</div>
              <ScoreGauge score={Math.round(bestDog.score)} size="sm" color={dogColor} />
              <div style={{ fontSize: 8, color: dogColor, fontFamily: "monospace", marginTop: 3, maxWidth: 72, textAlign: "center" }}>
                {bestDog.team?.split(" ").pop()}
              </div>
              {game.live_dog?.live_dog_score != null && (
                <div style={{ marginTop: 4 }}>
                  <div style={{ fontSize: 7, color: "#fbbf24", letterSpacing: 1.5 }}>LIVE</div>
                  <div style={{ fontSize: 12, color: "#fbbf24", fontFamily: "monospace", fontWeight: 700 }}>
                    {Math.round(game.live_dog.live_dog_score)}
                    {game.live_dog.delta !== 0 && (
                      <span style={{ fontSize: 9, marginLeft: 3, color: game.live_dog.delta > 0 ? "#00ff87" : "#ff3b3b" }}>
                        {game.live_dog.delta > 0 ? "▲" : "▼"}{Math.abs(game.live_dog.delta)}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Verdict + alert */}
        <div style={{
          background: cfg.color + "12", border: `1px solid ${cfg.color}30`,
          borderRadius: 4, padding: "7px 14px", marginBottom: 12, textAlign: "center",
        }}>
          <span style={{ color: cfg.color, fontFamily: "monospace", fontWeight: 700, fontSize: 11, letterSpacing: 2 }}>
            {cfg.label}
          </span>
        </div>

        {correlation.alert && (
          <div style={{
            background: "#a78bfa15", border: "1px solid #a78bfa30",
            borderRadius: 4, padding: "7px 14px", marginBottom: 12,
            fontSize: 10, color: "#a78bfa", fontFamily: "monospace", textAlign: "center",
          }}>
            {correlation.alert}
          </div>
        )}

        {/* Closing vs Live odds */}
        <OddsRow
          line={line}
          moneyline={game.moneyline_data}
          awayTeam={game.away_team}
          homeTeam={game.home_team}
        />

        {/* Component bars */}
        <VariableBar label="Park Factor"     score={game.park_factor_score}      weight={25} />
        <VariableBar label="Pitching Stack"  score={game.pitcher_score}           weight={25} note={pitcherNote} />
        <VariableBar label="Weather"         score={game.weather_score}           weight={15} note={weatherNote} />
        <VariableBar label="Team Fatigue"    score={game.fatigue_score}           weight={9}  note={fatigueNote} />
        <VariableBar label="Line Movement"   score={game.line_movement_score}     weight={10} note={line.signal} />
        <VariableBar label="Umpire Zone"     score={game.umpire_score}            weight={8}  note={game.umpire_data?.umpire_name} />
        <VariableBar label="Bullpen Status"  score={game.bullpen_score}           weight={8}  note={bullpenNote} />

        {/* Expand for dog detail */}
        <button
          onClick={() => setExpanded(e => !e)}
          style={{
            background: "transparent", border: "1px solid #1e1e1e",
            color: "#444", width: "100%", padding: "6px", marginTop: 8,
            borderRadius: 4, fontSize: 9, fontFamily: "monospace",
            letterSpacing: 2, cursor: "pointer", textTransform: "uppercase",
          }}
        >
          {expanded ? "▲ HIDE DOG DETAIL" : "▼ DOG SCORE DETAIL"}
        </button>

        {expanded && (
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #1a1a1a" }}>
            <div style={{ fontSize: 10, color: "#555", letterSpacing: 2, marginBottom: 10, fontFamily: "monospace" }}>
              DOG ANALYSIS — {bestDog.team?.toUpperCase()} ({bestDog.verdict?.toUpperCase()})
            </div>
            {Object.entries(dog.home_dog_detail?.components || {}).map(([key, val]) => (
              <VariableBar
                key={key}
                label={key.replace(/_/g, " ")}
                score={val}
              />
            ))}
            <div style={{ marginTop: 10 }}>
              {awayFatigue && (
                <div style={{ fontSize: 9, color: "#444", fontFamily: "monospace", marginBottom: 3 }}>
                  {game.away_team}: {awayFatigue.consecutive_road_games} consec. road · {awayFatigue.travel_penalty > 0 ? `west travel penalty` : "no travel penalty"} {awayFatigue.is_dagn ? "· DAGN" : ""}
                </div>
              )}
              {homeFatigue && (
                <div style={{ fontSize: 9, color: "#444", fontFamily: "monospace" }}>
                  {game.home_team}: {homeFatigue.consecutive_road_games > 0 ? `${homeFatigue.consecutive_road_games} road` : "home"} · {homeFatigue.rest_days}d rest
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div style={{ borderTop: "1px solid #1a1a1a", paddingTop: 16, marginTop: 8 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
        {Object.entries(VERDICT_CONFIG).map(([key, { color, label }]) => (
          <div key={key} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", background: color }} />
            <span style={{ fontSize: 9, color: "#444", letterSpacing: 1, fontFamily: "monospace" }}>{label}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 16 }}>
        {Object.entries(DOG_CONFIG).slice(0, 2).map(([key, { color }]) => (
          <div key={key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", background: color }} />
            <span style={{ fontSize: 9, color: "#444", fontFamily: "monospace" }}>{key}</span>
          </div>
        ))}
        <span style={{ fontSize: 9, color: "#333", fontFamily: "monospace" }}>🔥 = Under + Dog aligned</span>
      </div>
    </div>
  );
}

// ─── EDGE TAB COMPONENTS ──────────────────────────────────────────────────────

function americanOdds(price) {
  if (price == null) return "—";
  return price > 0 ? `+${price}` : `${price}`;
}

function MiniScore({ score, color }) {
  return (
    <div style={{
      width: 56, height: 56, borderRadius: "50%",
      border: `2px solid ${color}`,
      display: "flex", alignItems: "center", justifyContent: "center",
      background: `radial-gradient(circle, ${color}15 0%, transparent 70%)`,
      boxShadow: `0 0 12px ${color}30`,
    }}>
      <span style={{ fontSize: 18, fontWeight: 900, color, fontFamily: "monospace" }}>
        {score != null ? Math.round(score) : "--"}
      </span>
    </div>
  );
}

function EdgePlayCard({ game, kind, score, verdict, color, line, label, subtitle, factors, bestBook }) {
  return (
    <div style={{
      background: "#0a0a0a", border: `1px solid ${color}30`, borderRadius: 8,
      padding: "14px 16px", marginBottom: 10,
      display: "flex", alignItems: "center", gap: 14,
    }}>
      <MiniScore score={score} color={color} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: "#fff", fontWeight: 700 }}>
            {game.away_team} @ {game.home_team}
          </span>
          <span style={{ fontSize: 9, color: color, letterSpacing: 1.5, fontWeight: 700 }}>
            {verdict}
          </span>
        </div>
        {label && (
          <div style={{ fontSize: 11, color: "#a78bfa", marginTop: 4, fontFamily: "monospace" }}>
            {label}
            {line != null && <span style={{ color: "#fff", marginLeft: 6 }}>U{line}</span>}
            {bestBook && <span style={{ color: "#666", marginLeft: 6 }}>· best @ {bestBook}</span>}
          </div>
        )}
        {subtitle && (
          <div style={{ fontSize: 9, color: "#555", marginTop: 3, fontFamily: "monospace" }}>
            {subtitle}
          </div>
        )}
        {factors && factors.length > 0 && (
          <div style={{ fontSize: 9, color: "#666", marginTop: 4, fontFamily: "monospace" }}>
            {factors.slice(0, 3).join(" · ")}
          </div>
        )}
      </div>
    </div>
  );
}

function SectionHeader({ title, subtitle, count }) {
  return (
    <div style={{ marginTop: 28, marginBottom: 12, borderBottom: "1px solid #1a1a1a", paddingBottom: 10 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <div style={{ fontSize: 14, color: "#fff", fontWeight: 900, letterSpacing: 2 }}>{title}</div>
        <span style={{ fontSize: 9, color: "#444", fontFamily: "monospace" }}>{count} plays</span>
      </div>
      <div style={{ fontSize: 10, color: "#444", marginTop: 4, fontFamily: "monospace" }}>{subtitle}</div>
    </div>
  );
}

function EdgeBoard({ games }) {
  // NRFI sorted by probability desc
  const nrfi = [...games]
    .filter(g => g.nrfi?.nrfi_probability != null)
    .sort((a, b) => (b.nrfi?.nrfi_probability ?? 0) - (a.nrfi?.nrfi_probability ?? 0))
    .slice(0, 8);

  const f5 = [...games]
    .filter(g => g.f5?.f5_score != null)
    .sort((a, b) => (b.f5?.f5_score ?? 0) - (a.f5?.f5_score ?? 0))
    .slice(0, 8);

  const tt = [...games]
    .filter(g => g.team_totals?.best_score != null)
    .sort((a, b) => (b.team_totals?.best_score ?? 0) - (a.team_totals?.best_score ?? 0))
    .slice(0, 8);

  const late = [...games]
    .filter(g => g.late_innings?.late_score != null)
    .sort((a, b) => (b.late_innings?.late_score ?? 0) - (a.late_innings?.late_score ?? 0))
    .slice(0, 8);

  const nrfiColor = (p) => p >= 72 ? "#00ff87" : p >= 62 ? "#ffd700" : p >= 54 ? "#ff9500" : "#555";
  const scoreColor = (s) => s >= 78 ? "#00ff87" : s >= 66 ? "#ffd700" : s >= 55 ? "#ff9500" : "#555";
  const lateColor  = (s) => s >= 76 ? "#00ff87" : s >= 64 ? "#ffd700" : s >= 54 ? "#ff9500" : "#555";

  return (
    <div>
      <div style={{
        background: "#0a0a0a", border: "1px solid #1a1a1a", borderRadius: 8,
        padding: "14px 18px", marginBottom: 20,
      }}>
        <div style={{ fontSize: 11, color: "#00ff87", letterSpacing: 3, fontWeight: 900 }}>
          PRE-FLOP CHIP STACK
        </div>
        <div style={{ fontSize: 10, color: "#555", marginTop: 6, lineHeight: 1.5 }}>
          Bets that start you ahead. NRFI wins by minute 10. F5 isolates to starters and removes
          bullpen variance. Team totals only need ONE side to underperform.
        </div>
      </div>

      <SectionHeader
        title="🥇 NRFI BOARD"
        subtitle="No Run First Inning — probability both teams scoreless in inning 1"
        count={nrfi.length}
      />
      {nrfi.map(g => (
        <EdgePlayCard
          key={`nrfi-${g.game_pk}`}
          game={g}
          kind="nrfi"
          score={g.nrfi.nrfi_probability}
          verdict={g.nrfi.verdict}
          color={nrfiColor(g.nrfi.nrfi_probability)}
          label={`Away SP holds ${g.nrfi.away_pitcher_hold_pct}% · Home SP holds ${g.nrfi.home_pitcher_hold_pct}%`}
          factors={g.nrfi.key_factors}
        />
      ))}

      <SectionHeader
        title="🎯 F5 UNDERS"
        subtitle="First 5 innings — just the starting pitchers, no bullpen variance"
        count={f5.length}
      />
      {f5.map(g => (
        <EdgePlayCard
          key={`f5-${g.game_pk}`}
          game={g}
          kind="f5"
          score={g.f5.f5_score}
          verdict={g.f5.verdict}
          color={scoreColor(g.f5.f5_score)}
          line={g.f5.projected_f5_line}
          label="Projected F5"
          subtitle={`Pitcher ${g.f5.components.pitcher} · Park ${g.f5.components.park} · Wx ${g.f5.components.weather} · Ump ${g.f5.components.umpire}`}
        />
      ))}

      <SectionHeader
        title="🔋 LATE INNINGS / FULL 9"
        subtitle="Bullpen-leveraged full-game under — where the real liquidity lives"
        count={late.length}
      />
      {late.map(g => (
        <EdgePlayCard
          key={`late-${g.game_pk}`}
          game={g}
          kind="late"
          score={g.late_innings.late_score}
          verdict={g.late_innings.verdict}
          color={lateColor(g.late_innings.late_score)}
          line={g.late_innings.full_game_total}
          label="Full game"
          subtitle={`Pen avg ${g.late_innings.components.bullpen_combined} · weaker ${g.late_innings.components.weaker_bullpen} · SP avg ${g.late_innings.components.starter_avg}`}
          factors={g.late_innings.notes}
        />
      ))}

      <SectionHeader
        title="⚡ TEAM TOTAL UNDERS"
        subtitle="One side has to underperform — surgical when one offense is cold"
        count={tt.length}
      />
      {tt.map(g => (
        <EdgePlayCard
          key={`tt-${g.game_pk}`}
          game={g}
          kind="tt"
          score={g.team_totals.best_score}
          verdict={g.team_totals.best_verdict}
          color={scoreColor(g.team_totals.best_score)}
          line={g.team_totals.best_projected_total}
          label={g.team_totals.best_team}
          bestBook={g.best_prices?.best_under_book}
        />
      ))}
    </div>
  );
}

// ─── AI PICKS TAB ────────────────────────────────────────────────────────────

function LiveTracker({ games }) {
  const live = games.filter(g => g.abstract_state === "Live");
  if (!live.length) return null;

  const underLeads = live
    .filter(g => g.live_under?.live_under_score != null && g.live_under.live_under_score >= 55)
    .sort((a, b) => (b.live_under?.live_under_score ?? 0) - (a.live_under?.live_under_score ?? 0));

  const dogLeads = live
    .filter(g => g.live_dog?.live_dog_score != null && g.live_dog.live_dog_score >= 55)
    .sort((a, b) => (b.live_dog?.live_dog_score ?? 0) - (a.live_dog?.live_dog_score ?? 0));

  return (
    <div>
      <div style={{
        background: "#fbbf2410", border: "1px solid #fbbf2430", borderRadius: 8,
        padding: "14px 18px", marginBottom: 20,
      }}>
        <div style={{ fontSize: 11, color: "#fbbf24", letterSpacing: 3, fontWeight: 900 }}>
          ● LIVE TRACKER
        </div>
        <div style={{ fontSize: 10, color: "#555", marginTop: 5 }}>
          Pre-game picks locked. Tracking {live.length} in-progress games for under pace and dog position.
        </div>
      </div>

      {underLeads.length > 0 && (
        <>
          <SectionHeader title="📉 UNDER PACE" subtitle="Games still tracking well for the under — live score" count={underLeads.length} />
          {underLeads.map(g => {
            const lu = g.live_under || {};
            const ls = g.live_score || {};
            const color = lu.live_under_score >= 70 ? "#00ff87" : lu.live_under_score >= 60 ? "#ffd700" : "#ff9500";
            const delta = lu.delta ?? 0;
            return (
              <div key={`lu-${g.game_pk}`} style={{
                background: "#0a0a0a", border: `1px solid ${color}25`,
                borderRadius: 8, padding: "12px 16px", marginBottom: 8,
                display: "flex", alignItems: "center", gap: 14,
              }}>
                <div style={{ textAlign: "center", minWidth: 52 }}>
                  <div style={{ fontSize: 22, fontWeight: 900, color, fontFamily: "monospace" }}>
                    {Math.round(lu.live_under_score)}
                  </div>
                  {delta !== 0 && (
                    <div style={{ fontSize: 9, color: delta > 0 ? "#00ff87" : "#ff3b3b", fontFamily: "monospace" }}>
                      {delta > 0 ? "▲" : "▼"}{Math.abs(delta)}
                    </div>
                  )}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, color: "#fff", fontWeight: 700 }}>
                    {g.away_team} @ {g.home_team}
                  </div>
                  <div style={{ fontSize: 10, color: "#fbbf24", fontFamily: "monospace", marginTop: 3 }}>
                    {g.away_team?.split(" ").pop()} {ls.away_runs ?? 0} — {ls.home_runs ?? 0} {g.home_team?.split(" ").pop()}
                    <span style={{ color: "#666", marginLeft: 8 }}>
                      {ls.inning_half?.startsWith("T") ? "▲" : "▼"} {ls.inning}
                    </span>
                  </div>
                  <div style={{ fontSize: 9, color: "#555", marginTop: 3, fontFamily: "monospace" }}>
                    {lu.pace_note}
                    {g.line_movement?.closing_total != null && (
                      <span style={{ marginLeft: 8, color: "#444" }}>· closing O/U {g.line_movement.closing_total}</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </>
      )}

      {dogLeads.length > 0 && (
        <>
          <SectionHeader title="🐕 DOG STILL IN IT" subtitle="Underdogs still alive — live position score" count={dogLeads.length} />
          {dogLeads.map(g => {
            const ld = g.live_dog || {};
            const ls = g.live_score || {};
            const ds = g.dog_score || {};
            const actual = ds.actual_dog_side;
            const dogTeam = actual ? g[`${actual}_team`] : null;
            const color = ld.live_dog_score >= 75 ? "#a78bfa" : ld.live_dog_score >= 65 ? "#c4b5fd" : "#9ca3af";
            const delta = ld.delta ?? 0;
            const ml = g.moneyline_data;
            const dogMl = actual && ml ? ml[`closing_${actual}_ml`] : null;
            return (
              <div key={`ld-${g.game_pk}`} style={{
                background: "#0a0a0a", border: `1px solid ${color}25`,
                borderRadius: 8, padding: "12px 16px", marginBottom: 8,
                display: "flex", alignItems: "center", gap: 14,
              }}>
                <div style={{ textAlign: "center", minWidth: 52 }}>
                  <div style={{ fontSize: 22, fontWeight: 900, color, fontFamily: "monospace" }}>
                    {Math.round(ld.live_dog_score)}
                  </div>
                  {delta !== 0 && (
                    <div style={{ fontSize: 9, color: delta > 0 ? "#00ff87" : "#ff3b3b", fontFamily: "monospace" }}>
                      {delta > 0 ? "▲" : "▼"}{Math.abs(delta)}
                    </div>
                  )}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, color: "#fff", fontWeight: 700 }}>
                    {dogTeam || "—"} <span style={{ color: "#444", fontWeight: 400, fontSize: 10 }}>ML</span>
                    {dogMl != null && (
                      <span style={{ color: "#fbbf24", marginLeft: 8, fontSize: 10 }}>
                        {dogMl > 0 ? "+" : ""}{dogMl}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 10, color: "#fbbf24", fontFamily: "monospace", marginTop: 3 }}>
                    {g.away_team?.split(" ").pop()} {ls.away_runs ?? 0} — {ls.home_runs ?? 0} {g.home_team?.split(" ").pop()}
                    <span style={{ color: "#666", marginLeft: 8 }}>
                      {ls.inning_half?.startsWith("T") ? "▲" : "▼"} {ls.inning}
                    </span>
                  </div>
                  <div style={{ fontSize: 9, color: "#555", marginTop: 3, fontFamily: "monospace" }}>
                    {ld.pace_note}
                  </div>
                </div>
              </div>
            );
          })}
        </>
      )}

      {underLeads.length === 0 && dogLeads.length === 0 && (
        <div style={{ textAlign: "center", padding: 30, color: "#333", fontSize: 10, fontFamily: "monospace" }}>
          No live games currently tracking well. Check the SLATE tab for game details.
        </div>
      )}
    </div>
  );
}

function ParlayCard({ parlay, title, accentColor, icon, source }) {
  if (!parlay) return null;
  const hasLegs = parlay.legs && parlay.legs.length > 0;
  return (
    <div style={{
      background: "#0a0a0a", border: `2px solid ${hasLegs ? accentColor : "#333"}`, borderRadius: 10,
      padding: "18px 20px", marginBottom: 24,
      boxShadow: hasLegs ? `0 0 24px ${accentColor}20` : "none",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: hasLegs ? accentColor : "#555", letterSpacing: 3, fontWeight: 900 }}>
            {icon} {title}
          </div>
          <div style={{ fontSize: 9, color: "#666", marginTop: 4 }}>{parlay.note}</div>
          {parlay.structure && (
            <div style={{ fontSize: 9, color: accentColor, marginTop: 4, fontFamily: "monospace", letterSpacing: 0.5 }}>
              {parlay.structure}
            </div>
          )}
        </div>
        {hasLegs && (
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 22, color: accentColor, fontWeight: 900, fontFamily: "monospace" }}>
            {parlay.combined_odds}
          </div>
          <div style={{ fontSize: 9, color: "#666", fontFamily: "monospace" }}>
            ${parlay.payout_per_100}/$100
          </div>
        </div>
        )}
      </div>

      {!hasLegs && (
        <div style={{
          textAlign: "center", padding: "20px 0", color: "#444",
          fontSize: 10, letterSpacing: 2, fontFamily: "monospace",
        }}>
          ⏳ WAITING FOR LINES — REFRESHES AUTOMATICALLY
        </div>
      )}

      {hasLegs && parlay.legs.map((leg, i) => {
        const isUnder = leg.type === "UNDER";
        const isOver = leg.type === "OVER";
        const legColor = isUnder ? "#00ff87" : isOver ? "#fbbf24" : "#a78bfa";
        const ca = leg.cover_analysis || {};
        return (
          <div key={i} style={{
            borderTop: "1px solid #1a1a1a",
            padding: "14px 0",
            display: "flex", gap: 12, alignItems: "flex-start",
          }}>
            <div style={{
              width: 26, height: 26, borderRadius: "50%",
              background: legColor + "20", color: legColor,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12, fontWeight: 900, flexShrink: 0, marginTop: 2,
            }}>{i + 1}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              {leg.leg_role && (
                <div style={{ fontSize: 8, color: legColor, letterSpacing: 1.5, fontWeight: 700, marginBottom: 3 }}>
                  {leg.leg_role}
                </div>
              )}
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 13, color: "#fff", fontWeight: 700 }}>{leg.play}</span>
                <span style={{ color: "#555", fontWeight: 400, fontSize: 10 }}>{americanOdds(leg.odds)}</span>
                <EdgeChip edge={leg.edge} />
                {leg.implied_pct != null && (
                  <span style={{ color: "#888", fontSize: 9 }}>({leg.implied_pct}% implied)</span>
                )}
                {leg.best_book && (
                  <span style={{ color: "#60a5fa", fontSize: 9 }}>best @ {leg.best_book}</span>
                )}
                <AddPill leg={leg} source={source || title} accentColor={accentColor} />
              </div>
              <div style={{ fontSize: 10, color: "#666", marginTop: 2, fontFamily: "monospace" }}>
                {leg.matchup}
              </div>

              {isUnder && leg.projected_floor && (
                <div style={{ marginTop: 8, background: "#00ff8708", border: "1px solid #00ff8720", borderRadius: 4, padding: "7px 10px" }}>
                  <div style={{ fontSize: 9, color: "#00ff87", letterSpacing: 1.5, fontWeight: 700, marginBottom: 4 }}>
                    FLOOR PROJECTION — game ends as low as {leg.projected_floor} total runs
                  </div>
                  {(leg.floor_reasoning || []).map((r, j) => (
                    <div key={j} style={{ fontSize: 9, color: "#666", marginBottom: 2, lineHeight: 1.4 }}>• {r}</div>
                  ))}
                  {leg.reasoning && <div style={{ fontSize: 9, color: "#555", marginTop: 4, lineHeight: 1.4 }}>{leg.reasoning}</div>}
                </div>
              )}

              {isOver && (
                <div style={{ marginTop: 8, background: "#fbbf2408", border: "1px solid #fbbf2420", borderRadius: 4, padding: "7px 10px" }}>
                  <div style={{ fontSize: 9, color: "#fbbf24", letterSpacing: 1.5, fontWeight: 700, marginBottom: 4 }}>
                    OVER DRIVERS
                  </div>
                  {(leg.over_reasons || []).map((r, j) => (
                    <div key={j} style={{ fontSize: 9, color: "#888", marginBottom: 2, lineHeight: 1.4 }}>• {r}</div>
                  ))}
                </div>
              )}

              {!isUnder && !isOver && ca.cover_label && (
                <div style={{ marginTop: 8, background: "#a78bfa08", border: "1px solid #a78bfa20", borderRadius: 4, padding: "7px 10px" }}>
                  <div style={{ display: "flex", gap: 10, alignItems: "baseline", marginBottom: 4, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 9, color: "#a78bfa", letterSpacing: 1.5, fontWeight: 700 }}>{ca.cover_label}</span>
                    <span style={{ fontSize: 9, color: "#666" }}>{ca.cover_pct} cover prob</span>
                    <span style={{ fontSize: 9, color: ca.win_by_margin ? "#00ff87" : "#555" }}>
                      {ca.win_by_margin ? "⚡ WIN BY 2+ IN PLAY" : ca.win_label}
                    </span>
                  </div>
                  {(ca.margin_notes || []).map((n, j) => (
                    <div key={j} style={{ fontSize: 9, color: "#666", marginBottom: 2, lineHeight: 1.4 }}>• {n}</div>
                  ))}
                  {leg.reasoning && <div style={{ fontSize: 9, color: "#555", marginTop: 4 }}>{leg.reasoning}</div>}
                </div>
              )}

              {!isUnder && !isOver && !ca.cover_label && (leg.fav_reasons?.length > 0) && (
                <div style={{ marginTop: 8, background: "#fbbf2408", border: "1px solid #fbbf2420", borderRadius: 4, padding: "7px 10px" }}>
                  <div style={{ fontSize: 9, color: "#fbbf24", letterSpacing: 1.5, fontWeight: 700, marginBottom: 4 }}>
                    FAVORITE EDGE
                  </div>
                  {leg.fav_reasons.map((r, j) => (
                    <div key={j} style={{ fontSize: 9, color: "#888", marginBottom: 2, lineHeight: 1.4 }}>• {r}</div>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function AlreadyWinningCard({ parlay }) {
  if (!parlay) return null;
  const hasLegs = parlay.legs && parlay.legs.length > 0;
  const accent = "#22d3ee";
  return (
    <div style={{
      background: "linear-gradient(135deg, #0a0a0a 0%, #001a1f 100%)",
      border: `2px solid ${hasLegs ? accent : "#0d2a2f"}`, borderRadius: 10,
      padding: "18px 20px", marginBottom: 24,
      boxShadow: hasLegs ? `0 0 28px ${accent}25` : "none",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: hasLegs ? accent : "#2a5a60", letterSpacing: 3, fontWeight: 900 }}>
            🛡️ ALREADY WINNING PARLAY
          </div>
          <div style={{ fontSize: 9, color: "#666", marginTop: 4 }}>{parlay.note}</div>
          {parlay.structure && (
            <div style={{ fontSize: 9, color: accent, marginTop: 4, fontFamily: "monospace", letterSpacing: 0.5 }}>
              {parlay.structure}
            </div>
          )}
        </div>
        {hasLegs && (
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 22, color: accent, fontWeight: 900, fontFamily: "monospace" }}>
              {parlay.combined_odds}
            </div>
            <div style={{ fontSize: 9, color: "#666", fontFamily: "monospace" }}>
              ${parlay.payout_per_100}/$100
            </div>
          </div>
        )}
      </div>

      {hasLegs && (
        <div style={{
          fontSize: 9, color: "#a5f3fc", marginBottom: 10, lineHeight: 1.5,
          padding: "10px 12px", background: `${accent}10`, borderRadius: 4,
          border: `1px solid ${accent}30`,
        }}>
          🛡️ YOU'RE IN A WINNING POSITION BEFORE PITCH 1 — Dogs need to <strong>not get blown out</strong> (+1.5 cushion). Unders need scoring to happen <strong>to beat you</strong>.
        </div>
      )}

      {!hasLegs && (
        <div style={{ textAlign: "center", padding: "20px 0", color: "#444", fontSize: 10, letterSpacing: 2, fontFamily: "monospace" }}>
          ⏳ WAITING FOR LINES — REFRESHES AUTOMATICALLY
        </div>
      )}

      {hasLegs && parlay.legs.map((leg, i) => {
        const isDog = leg.type === "AW_DOG_RL";
        const legColor = isDog ? "#a78bfa" : "#22d3ee";
        const rank = leg.rank || (i + 1);
        const rankColors = { 1: "#00ff87", 2: "#fbbf24", 3: "#fb923c", 4: accent };
        const rankColor = rankColors[rank] || "#666";
        return (
          <div key={i} style={{
            borderTop: "1px solid #0d2a30",
            padding: "14px 0",
            display: "flex", gap: 12, alignItems: "flex-start",
          }}>
            <div style={{ flexShrink: 0, textAlign: "center", minWidth: 36 }}>
              <div style={{
                width: 32, height: 32, borderRadius: "50%",
                background: rankColor + "20", color: rankColor,
                border: `2px solid ${rankColor}60`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 14, fontWeight: 900, margin: "0 auto",
              }}>#{rank}</div>
              <div style={{ fontSize: 7, color: rankColor, marginTop: 4, fontFamily: "monospace", letterSpacing: 0.5, fontWeight: 700 }}>
                {leg.rank_label}
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 13, color: legColor, fontWeight: 700 }}>{leg.play}</span>
                {leg.odds != null && (
                  <span style={{ fontSize: 10, color: "#fbbf24", fontFamily: "monospace", fontWeight: 700 }}>
                    {leg.odds > 0 ? `+${leg.odds}` : leg.odds}
                  </span>
                )}
                <EdgeChip edge={leg.edge} />
                {leg.best_book && (
                  <span style={{ color: "#60a5fa", fontSize: 9 }}>best @ {leg.best_book}</span>
                )}
                <AddPill leg={leg} source="Already Winning" accentColor={legColor} />
              </div>
              <div style={{ fontSize: 10, color: "#666", marginTop: 2, fontFamily: "monospace" }}>{leg.matchup}</div>
              {leg.difficulty && (
                <div style={{ fontSize: 9, color: "#a5f3fc", marginTop: 5, fontFamily: "monospace", fontStyle: "italic" }}>
                  🛡️ {leg.difficulty}
                </div>
              )}
              {leg.reasoning && (
                <div style={{ fontSize: 9, color: "#888", marginTop: 4, lineHeight: 1.4 }}>{leg.reasoning}</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TeaseCard({ parlay }) {
  if (!parlay?.legs?.length) return null;
  return (
    <div style={{
      background: "#0a0a0a", border: "2px solid #06b6d4", borderRadius: 10,
      padding: "18px 20px", marginBottom: 24,
      boxShadow: "0 0 24px #06b6d420",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: "#06b6d4", letterSpacing: 3, fontWeight: 900 }}>
            🎯 TEASE PARLAY — {parlay.tease_amount?.toUpperCase()} TEASER
          </div>
          <div style={{ fontSize: 9, color: "#666", marginTop: 4 }}>{parlay.note}</div>
          {parlay.structure && (
            <div style={{ fontSize: 9, color: "#06b6d4", marginTop: 4, fontFamily: "monospace", letterSpacing: 0.5 }}>
              {parlay.structure}
            </div>
          )}
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 22, color: "#06b6d4", fontWeight: 900, fontFamily: "monospace" }}>
            {parlay.combined_odds}
          </div>
          <div style={{ fontSize: 9, color: "#666", fontFamily: "monospace" }}>
            ${parlay.payout_per_100}/$100
          </div>
        </div>
      </div>

      <div style={{ fontSize: 9, color: "#888", marginBottom: 10, lineHeight: 1.5, padding: "6px 10px", background: "#06b6d408", borderRadius: 4 }}>
        Each line moved {parlay.tease_amount} in your favor. Higher hit-rate, capped payout.
        Every leg must still win at the new line.
      </div>

      {parlay.legs.map((leg, i) => {
        const isUnder = leg.type === "TEASE_UNDER";
        const accent = isUnder ? "#00ff87" : "#a78bfa";
        return (
          <div key={i} style={{
            borderTop: "1px solid #1a1a1a",
            padding: "12px 0",
            display: "flex", gap: 12, alignItems: "flex-start",
          }}>
            <div style={{
              width: 26, height: 26, borderRadius: "50%",
              background: accent + "20", color: accent,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12, fontWeight: 900, flexShrink: 0,
            }}>{i + 1}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 13, color: "#fff", fontWeight: 700 }}>{leg.play}</span>
                <span style={{ fontSize: 9, color: "#06b6d4", fontFamily: "monospace" }}>
                  was {leg.original_line}
                </span>
                <span style={{ fontSize: 9, color: "#666" }}>{leg.tease_direction}</span>
                {leg.best_book && (
                  <span style={{ color: "#60a5fa", fontSize: 9 }}>best @ {leg.best_book}</span>
                )}
              </div>
              <div style={{ fontSize: 10, color: "#666", marginTop: 2, fontFamily: "monospace" }}>
                {leg.matchup}
              </div>
              {leg.reasoning && (
                <div style={{ fontSize: 9, color: "#777", marginTop: 4, lineHeight: 1.4 }}>
                  {leg.reasoning}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PleaserCard({ parlay }) {
  if (!parlay?.legs?.length) return null;
  return (
    <div style={{
      background: "#0a0a0a", border: "2px solid #f43f5e", borderRadius: 10,
      padding: "18px 20px", marginBottom: 24,
      boxShadow: "0 0 24px #f43f5e25",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: "#f43f5e", letterSpacing: 3, fontWeight: 900 }}>
            😈 THE PLEASER PARLAY — REVERSE TEASER
          </div>
          <div style={{ fontSize: 9, color: "#666", marginTop: 4 }}>{parlay.note}</div>
          {parlay.structure && (
            <div style={{ fontSize: 9, color: "#f43f5e", marginTop: 4, fontFamily: "monospace", letterSpacing: 0.5 }}>
              {parlay.structure}
            </div>
          )}
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 24, color: "#f43f5e", fontWeight: 900, fontFamily: "monospace" }}>
            {parlay.combined_odds}
          </div>
          <div style={{ fontSize: 9, color: "#666", fontFamily: "monospace" }}>
            ${parlay.payout_per_100}/$100
          </div>
        </div>
      </div>

      <div style={{
        fontSize: 9, color: "#fda4af", marginBottom: 10, lineHeight: 1.5,
        padding: "8px 12px", background: "#f43f5e10", borderRadius: 4,
        border: "1px solid #f43f5e20",
      }}>
        ⚠ HIGH RISK · HIGH REWARD — every line moved {parlay.please_amount} <strong>AGAINST</strong> you.
        Dogs must win outright by 2+. Faves must cover -1.5. Unders must hit a tougher number.
        Hits rare — payout monster.
      </div>

      {parlay.legs.map((leg, i) => {
        const isUnder = leg.type === "PLEASE_UNDER";
        const isDog = leg.type === "PLEASE_DOG_RL";
        const accent = isUnder ? "#00ff87" : isDog ? "#a78bfa" : "#fb7185";
        // Rank-based intensity: #1 brightest, #4 dimmest
        const rank = leg.rank || (i + 1);
        const rankColors = { 1: "#00ff87", 2: "#fbbf24", 3: "#fb923c", 4: "#f43f5e" };
        const rankColor = rankColors[rank] || "#666";
        return (
          <div key={i} style={{
            borderTop: "1px solid #1a1a1a",
            padding: "14px 0",
            display: "flex", gap: 12, alignItems: "flex-start",
          }}>
            <div style={{ flexShrink: 0, textAlign: "center", minWidth: 36 }}>
              <div style={{
                width: 32, height: 32, borderRadius: "50%",
                background: rankColor + "20", color: rankColor,
                border: `2px solid ${rankColor}60`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 14, fontWeight: 900, margin: "0 auto",
              }}>#{rank}</div>
              <div style={{
                fontSize: 7, color: rankColor, marginTop: 4,
                fontFamily: "monospace", letterSpacing: 0.5, fontWeight: 700,
                lineHeight: 1.1,
              }}>
                {leg.rank_label}
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 13, color: accent, fontWeight: 700 }}>{leg.play}</span>
                <span style={{ fontSize: 9, color: "#f43f5e", fontFamily: "monospace" }}>
                  was {leg.original_line}
                </span>
                {leg.best_book && (
                  <span style={{ color: "#60a5fa", fontSize: 9 }}>best @ {leg.best_book}</span>
                )}
              </div>
              <div style={{ fontSize: 10, color: "#666", marginTop: 2, fontFamily: "monospace" }}>
                {leg.matchup}
              </div>
              {leg.difficulty && (
                <div style={{
                  fontSize: 9, color: "#fda4af", marginTop: 5, fontFamily: "monospace",
                  fontStyle: "italic",
                }}>
                  ⚡ {leg.difficulty}
                </div>
              )}
              {leg.reasoning && (
                <div style={{ fontSize: 9, color: "#777", marginTop: 4, lineHeight: 1.4 }}>
                  {leg.reasoning}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BestEdgeCard({ parlay }) {
  if (!parlay) return null;
  const legs = parlay.legs || [];
  const hasLegs = legs.length > 0;
  const accentColor = "#f59e0b";
  const glowColor = "#f59e0b";

  const TYPE_COLOR = {
    BE_UNDER:  "#00ff87",
    BE_FAV_ML: "#fb7185",
    BE_FAV_RL: "#f97316",
    BE_DOG_ML: "#a78bfa",
    BE_DOG_RL: "#818cf8",
  };
  const TYPE_LABEL = {
    BE_UNDER:  "UNDER",
    BE_FAV_ML: "FAVE ML",
    BE_FAV_RL: "FAVE -1.5",
    BE_DOG_ML: "DOG ML",
    BE_DOG_RL: "DOG +1.5",
  };

  // Always show 4 slots
  const SLOTS = [1, 2, 3, 4].map((n, i) => legs[i] ? legs[i] : { _tbd: true, rank: n });

  return (
    <div style={{
      background: "linear-gradient(135deg, #0a0a0a 0%, #1a1100 60%, #0d0a00 100%)",
      border: `2px solid ${hasLegs ? accentColor : "#2a2000"}`, borderRadius: 10,
      padding: "18px 20px", marginBottom: 24,
      boxShadow: hasLegs ? `0 0 36px ${glowColor}30` : "none",
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: hasLegs ? accentColor : "#555", letterSpacing: 3, fontWeight: 900 }}>
            🧠💰 BEST EDGE PARLAY
          </div>
          <div style={{ fontSize: 9, color: "#888", marginTop: 3 }}>
            Pure signal — only legs clearing +3% EV make the cut
          </div>
          {parlay.note && (
            <div style={{ fontSize: 8, color: "#666", marginTop: 3, fontFamily: "monospace" }}>
              {parlay.note}
            </div>
          )}
        </div>
        {hasLegs && (
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 28, color: accentColor, fontWeight: 900, fontFamily: "monospace", textShadow: `0 0 14px ${glowColor}50` }}>
              {parlay.combined_odds}
            </div>
            <div style={{ fontSize: 9, color: "#888", fontFamily: "monospace" }}>
              ${parlay.payout_per_100?.toLocaleString()}/$100
            </div>
          </div>
        )}
      </div>

      {/* EV banner */}
      {hasLegs && parlay.avg_leg_ev != null && (
        <div style={{
          fontSize: 9, color: "#fde68a", marginBottom: 10, lineHeight: 1.5,
          padding: "8px 12px", background: "#f59e0b12", borderRadius: 4,
          border: "1px solid #f59e0b30",
        }}>
          ⚡ Every leg cleared <strong>EDGE tier (+3% EV)</strong> — model's highest-conviction plays today.
          Avg leg EV: <strong>+{parlay.avg_leg_ev}%</strong>
        </div>
      )}

      {/* Legs */}
      {SLOTS.map((leg, i) => {
        const legColor = leg._tbd ? "#333" : (TYPE_COLOR[leg.type] || accentColor);
        const typeLabel = leg._tbd ? "" : (TYPE_LABEL[leg.type] || leg.type);
        const rank = leg.rank || (i + 1);
        const e = leg.edge || {};

        return (
          <div key={i} style={{
            borderTop: "1px solid #1a1a1a",
            padding: "13px 0",
            display: "flex", gap: 12, alignItems: "flex-start",
            background: leg._tbd ? "#ffffff03" : `${legColor}07`,
            borderLeft: `2px solid ${leg._tbd ? "#333" : legColor + "40"}`,
            paddingLeft: 10, borderRadius: "0 4px 4px 0", marginBottom: 2,
            opacity: leg._tbd ? 0.4 : 1,
          }}>
            {/* Rank bubble */}
            <div style={{ flexShrink: 0, textAlign: "center", minWidth: 36 }}>
              <div style={{
                width: 32, height: 32, borderRadius: "50%",
                background: legColor + "20", color: legColor,
                border: `2px solid ${legColor}60`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 13, fontWeight: 900, margin: "0 auto",
              }}>#{rank}</div>
              {typeLabel && (
                <div style={{
                  fontSize: 6, color: legColor, marginTop: 3,
                  fontFamily: "monospace", letterSpacing: 0.3, fontWeight: 700, lineHeight: 1.1,
                }}>
                  {typeLabel}
                </div>
              )}
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
              {leg._tbd ? (
                <div style={{ fontSize: 12, color: "#555", fontFamily: "monospace", letterSpacing: 2, paddingTop: 6 }}>
                  ⏳ PICK TBD — UPDATING AS LINES POST
                </div>
              ) : (
                <>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 13, color: legColor, fontWeight: 700 }}>{leg.play}</span>
                    {leg.odds != null && (
                      <span style={{ fontSize: 10, color: "#fbbf24", fontFamily: "monospace", fontWeight: 700 }}>
                        {leg.odds > 0 ? `+${leg.odds}` : leg.odds}
                      </span>
                    )}
                    {/* Inline EV badge */}
                    {e.edge_pct != null && (
                      <span style={{
                        fontSize: 9, fontFamily: "monospace", fontWeight: 800,
                        color: e.color || accentColor,
                        background: (e.color || accentColor) + "18",
                        border: `1px solid ${(e.color || accentColor)}50`,
                        padding: "1px 6px", borderRadius: 3, letterSpacing: 0.5,
                      }}>
                        {e.icon} {e.tier} {e.edge_pct > 0 ? `+${e.edge_pct}` : e.edge_pct}%
                      </span>
                    )}
                    <AddPill leg={leg} source="Best Edge" accentColor={legColor} />
                  </div>
                  <div style={{ fontSize: 10, color: "#666", marginTop: 2, fontFamily: "monospace" }}>
                    {leg.matchup}
                  </div>
                  {leg.reasoning && (
                    <div style={{ fontSize: 9, color: "#999", marginTop: 3, lineHeight: 1.4, fontStyle: "italic" }}>
                      {leg.reasoning}
                    </div>
                  )}
                  {e.our_prob != null && (
                    <div style={{ fontSize: 8, color: "#555", marginTop: 2, fontFamily: "monospace" }}>
                      model prob {(e.our_prob * 100).toFixed(1)}% · fair {e.our_fair_odds > 0 ? `+${e.our_fair_odds}` : e.our_fair_odds}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        );
      })}

      {/* Parlay-level edge footer */}
      {hasLegs && parlay.parlay_edge && parlay.parlay_edge.tier !== "UNPRICED" && (
        <div style={{
          marginTop: 10, padding: "6px 10px",
          background: (parlay.parlay_edge.color || "#555") + "10",
          border: `1px solid ${(parlay.parlay_edge.color || "#555")}30`,
          borderRadius: 4, display: "flex", alignItems: "center", gap: 8,
        }}>
          <span style={{ fontSize: 9, color: parlay.parlay_edge.color, fontFamily: "monospace", fontWeight: 700 }}>
            PARLAY EV {parlay.parlay_edge.icon} {parlay.parlay_edge.tier}
            {parlay.parlay_edge.edge_pct != null ? ` ${parlay.parlay_edge.edge_pct > 0 ? '+' : ''}${parlay.parlay_edge.edge_pct}%` : ""}
          </span>
          <span style={{ fontSize: 8, color: "#555", fontFamily: "monospace" }}>
            combined model prob {parlay.parlay_edge.our_prob != null ? `${(parlay.parlay_edge.our_prob * 100).toFixed(2)}%` : "—"}
          </span>
        </div>
      )}
    </div>
  );
}

function OutTheParkCard({ parlay }) {
  if (!parlay) return null;
  const hasLegs = parlay.legs && parlay.legs.length > 0;
  return (
    <div style={{
      background: "linear-gradient(135deg, #0a0a0a 0%, #1a0033 100%)",
      border: `2px solid ${hasLegs ? "#c026d3" : "#2a1a2a"}`, borderRadius: 10,
      padding: "18px 20px", marginBottom: 24,
      boxShadow: hasLegs ? "0 0 32px #c026d335" : "none",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: hasLegs ? "#e879f9" : "#555", letterSpacing: 3, fontWeight: 900 }}>
            🚀💥 OUT THE PARK PARLAY
          </div>
          <div style={{ fontSize: 9, color: "#888", marginTop: 4 }}>{parlay.note}</div>
          {parlay.structure && (
            <div style={{ fontSize: 9, color: "#e879f9", marginTop: 4, fontFamily: "monospace", letterSpacing: 0.5 }}>
              {parlay.structure}
            </div>
          )}
        </div>
        {hasLegs && (
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 28, color: "#e879f9", fontWeight: 900, fontFamily: "monospace", textShadow: "0 0 12px #c026d350" }}>
            {parlay.combined_odds}
          </div>
          <div style={{ fontSize: 9, color: "#888", fontFamily: "monospace" }}>
            ${parlay.payout_per_100?.toLocaleString()}/$100
          </div>
        </div>
        )}
      </div>

      {hasLegs && (
      <div style={{
        fontSize: 9, color: "#f0abfc", marginBottom: 10, lineHeight: 1.5,
        padding: "10px 12px", background: "#c026d310", borderRadius: 4,
        border: "1px solid #c026d330",
      }}>
        💀 MAXIMUM RISK · MAXIMUM REWARD — every line moved <strong>{parlay.otp_amount} AGAINST</strong> you.
        Dogs must win OUTRIGHT BY 2+. Faves must cover -1.5. Unders must hit 1.5 runs lower than the line.
        Hits the rarest. Cashes the biggest.
      </div>
      )}

      {(() => {
        const FAVE_COLOR = "#fb7185";
        const DOG_COLOR = "#a78bfa";
        const UNDER_COLOR = "#00ff87";
        const colorFor = (t) => t === "OTP_UNDER" ? UNDER_COLOR : t === "OTP_DOG_RL" ? DOG_COLOR : FAVE_COLOR;
        const labelFor = (t) => t === "OTP_UNDER" ? "📉 UNDER LAYER" : t === "OTP_DOG_RL" ? "🐕 UPSET LAYER" : "⭐ FAVE LAYER";
        const OTP_SLOTS = [
          { rank_label: "FAVE ANCHOR", type: "OTP_FAV_RL" },
          { rank_label: "FAVE SUPPORT", type: "OTP_FAV_RL" },
          { rank_label: "UPSET PICK", type: "OTP_DOG_RL" },
          { rank_label: "UNDER HAMMER", type: "OTP_UNDER" },
        ];
        const existingLegs = parlay.legs || [];
        const slots = OTP_SLOTS.map((slot, i) => existingLegs[i] ? existingLegs[i] : { ...slot, _tbd: true, rank: i + 1 });
        let prevType = null;
        return slots.map((leg, i) => {
          const legColor = leg._tbd ? "#333" : colorFor(leg.type);
          const rank = leg.rank || (i + 1);
          const showDivider = i > 0 && leg.type !== prevType;
          prevType = leg.type;
          return (
            <div key={i}>
              {showDivider && !leg._tbd && (
                <div style={{
                  display: "flex", alignItems: "center", gap: 8,
                  margin: "6px 0", opacity: 0.55,
                }}>
                  <div style={{ flex: 1, height: 1, background: "linear-gradient(90deg, transparent, #c026d3, transparent)" }} />
                  <span style={{ fontSize: 8, color: "#e879f9", fontFamily: "monospace", letterSpacing: 2, whiteSpace: "nowrap" }}>
                    {labelFor(leg.type)}
                  </span>
                  <div style={{ flex: 1, height: 1, background: "linear-gradient(90deg, transparent, #c026d3, transparent)" }} />
                </div>
              )}
              <div style={{
                borderTop: "1px solid #1a1a1a",
                padding: "14px 0",
                display: "flex", gap: 12, alignItems: "flex-start",
                background: leg._tbd ? "#ffffff04" : `${legColor}06`,
                borderLeft: `2px solid ${leg._tbd ? "#333" : legColor + "30"}`,
                paddingLeft: 10, borderRadius: "0 4px 4px 0", marginBottom: 2,
                opacity: leg._tbd ? 0.45 : 1,
              }}>
                <div style={{ flexShrink: 0, textAlign: "center", minWidth: 36 }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: "50%",
                    background: legColor + "20", color: legColor,
                    border: `2px solid ${legColor}60`,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 14, fontWeight: 900, margin: "0 auto",
                  }}>#{rank}</div>
                  <div style={{
                    fontSize: 7, color: legColor, marginTop: 4,
                    fontFamily: "monospace", letterSpacing: 0.5, fontWeight: 700,
                    lineHeight: 1.1,
                  }}>
                    {leg.rank_label}
                  </div>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {leg._tbd ? (
                    <div style={{ fontSize: 12, color: "#555", fontFamily: "monospace", letterSpacing: 2, paddingTop: 6 }}>
                      ⏳ PICK TBD — UPDATING AS LINES POST
                    </div>
                  ) : (
                    <>
                      <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 13, color: legColor, fontWeight: 700 }}>{leg.play}</span>
                        {leg.odds != null && (
                          <span style={{ fontSize: 10, color: "#fbbf24", fontFamily: "monospace", fontWeight: 700 }}>
                            {leg.odds > 0 ? `+${leg.odds}` : leg.odds}
                          </span>
                        )}
                        <EdgeChip edge={leg.edge} />
                        <span style={{ fontSize: 9, color: "#e879f9", fontFamily: "monospace" }}>
                          was {leg.original_line}
                        </span>
                        {leg.best_book && (
                          <span style={{ color: "#60a5fa", fontSize: 9 }}>best @ {leg.best_book}</span>
                        )}
                        <AddPill leg={leg} source="Out The Park" accentColor={legColor} />
                      </div>
                      <div style={{ fontSize: 10, color: "#666", marginTop: 2, fontFamily: "monospace" }}>
                        {leg.matchup}
                      </div>
                      {leg.difficulty && (
                        <div style={{ fontSize: 9, color: "#f0abfc", marginTop: 5, fontFamily: "monospace", fontStyle: "italic" }}>
                          ⚡ {leg.difficulty}
                        </div>
                      )}
                      {leg.reasoning && (
                        <div style={{ fontSize: 9, color: "#888", marginTop: 4, lineHeight: 1.4 }}>
                          {leg.reasoning}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        });
      })()}
    </div>
  );
}

function WayOutTheParkCard({ parlay }) {
  if (!parlay) return null;
  const hasLegs = parlay.legs && parlay.legs.length > 0;
  return (
    <div style={{
      background: "linear-gradient(135deg, #0a0a0a 0%, #2d0014 50%, #200033 100%)",
      border: `2px solid ${hasLegs ? "#ec4899" : "#2a1020"}`, borderRadius: 10,
      padding: "18px 20px", marginBottom: 24,
      boxShadow: hasLegs ? "0 0 36px #ec489940" : "none",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: hasLegs ? "#f9a8d4" : "#555", letterSpacing: 3, fontWeight: 900 }}>
            🚀💥💥 WAY OUT THE PARK
          </div>
          <div style={{ fontSize: 9, color: "#888", marginTop: 4 }}>{parlay.note}</div>
          {parlay.structure && (
            <div style={{ fontSize: 9, color: "#f9a8d4", marginTop: 4, fontFamily: "monospace", letterSpacing: 0.5 }}>
              {parlay.structure}
            </div>
          )}
        </div>
        {hasLegs && (
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 30, color: "#f9a8d4", fontWeight: 900, fontFamily: "monospace", textShadow: "0 0 16px #ec489960" }}>
            {parlay.combined_odds}
          </div>
          <div style={{ fontSize: 9, color: "#888", fontFamily: "monospace" }}>
            ${parlay.payout_per_100?.toLocaleString()}/$100
          </div>
        </div>
        )}
      </div>

      {hasLegs && (
      <div style={{
        fontSize: 9, color: "#fbcfe8", marginBottom: 10, lineHeight: 1.5,
        padding: "10px 12px", background: "#ec489918", borderRadius: 4,
        border: "1px solid #ec489940",
      }}>
        ☠️ THE WILDEST SWING ON THE BOARD — {parlay.wotp_amount}.
        Faves must <strong>WIN BY 3+ runs</strong>. Unders need to clear by <strong>2 full runs</strong>.
        Maximum chalk stretch. Lottery-ticket payouts.
      </div>
      )}

      {(() => {
        const FAVE_COLOR = "#fb7185";
        const UNDER_COLOR = "#00ff87";
        const WOTP_SLOTS = [
          { rank_label: "FAVE ANCHOR", type: "WOTP_FAV_RL" },
          { rank_label: "UNDER LOCK", type: "WOTP_UNDER" },
          { rank_label: "FAVE SUPPORT", type: "WOTP_FAV_RL" },
          { rank_label: "UNDER HAMMER", type: "WOTP_UNDER" },
        ];
        const existingLegs = parlay.legs || [];
        const slots = WOTP_SLOTS.map((slot, i) => existingLegs[i] ? existingLegs[i] : { ...slot, _tbd: true, rank: i + 1 });
        let prevType = null;
        return slots.map((leg, i) => {
          const isUnder = leg.type === "WOTP_UNDER";
          const legColor = leg._tbd ? "#333" : (isUnder ? UNDER_COLOR : FAVE_COLOR);
          const rank = leg.rank || (i + 1);
          const showDivider = i > 0 && !leg._tbd && isUnder !== (prevType === "WOTP_UNDER");
          prevType = leg.type;
          return (
            <div key={i}>
              {showDivider && (
                <div style={{
                  display: "flex", alignItems: "center", gap: 8,
                  margin: "6px 0", opacity: 0.5,
                }}>
                  <div style={{ flex: 1, height: 1, background: "linear-gradient(90deg, transparent, #ec4899, transparent)" }} />
                  <span style={{ fontSize: 8, color: "#f9a8d4", fontFamily: "monospace", letterSpacing: 2, whiteSpace: "nowrap" }}>
                    {isUnder ? "📉 UNDER LAYER" : "⭐ FAVE LAYER"}
                  </span>
                  <div style={{ flex: 1, height: 1, background: "linear-gradient(90deg, transparent, #ec4899, transparent)" }} />
                </div>
              )}
              <div style={{
                borderTop: "1px solid #1a1a1a",
                padding: "14px 0",
                display: "flex", gap: 12, alignItems: "flex-start",
                background: leg._tbd ? "#ffffff04" : `${legColor}06`,
                borderLeft: `2px solid ${leg._tbd ? "#333" : legColor + "30"}`,
                paddingLeft: 10, borderRadius: "0 4px 4px 0", marginBottom: 2,
                opacity: leg._tbd ? 0.45 : 1,
              }}>
                <div style={{ flexShrink: 0, textAlign: "center", minWidth: 36 }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: "50%",
                    background: legColor + "20", color: legColor,
                    border: `2px solid ${legColor}60`,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 14, fontWeight: 900, margin: "0 auto",
                  }}>#{rank}</div>
                  <div style={{
                    fontSize: 7, color: legColor, marginTop: 4,
                    fontFamily: "monospace", letterSpacing: 0.5, fontWeight: 700,
                    lineHeight: 1.1,
                  }}>
                    {leg.rank_label}
                  </div>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {leg._tbd ? (
                    <div style={{ fontSize: 12, color: "#555", fontFamily: "monospace", letterSpacing: 2, paddingTop: 6 }}>
                      ⏳ PICK TBD — UPDATING AS LINES POST
                    </div>
                  ) : (
                    <>
                      <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 13, color: legColor, fontWeight: 700 }}>{leg.play}</span>
                        {leg.odds != null && (
                          <span style={{ fontSize: 10, color: "#fbbf24", fontFamily: "monospace", fontWeight: 700 }}>
                            {leg.odds > 0 ? `+${leg.odds}` : leg.odds}
                          </span>
                        )}
                        <EdgeChip edge={leg.edge} />
                        <span style={{ fontSize: 9, color: "#ec4899", fontFamily: "monospace" }}>
                          was {leg.original_line}
                        </span>
                        {leg.best_book && (
                          <span style={{ color: "#60a5fa", fontSize: 9 }}>best @ {leg.best_book}</span>
                        )}
                        <AddPill leg={leg} source="Way Out The Park" accentColor={legColor} />
                      </div>
                      <div style={{ fontSize: 10, color: "#666", marginTop: 2, fontFamily: "monospace" }}>
                        {leg.matchup}
                      </div>
                      {leg.difficulty && (
                        <div style={{ fontSize: 9, color: "#fbcfe8", marginTop: 5, fontFamily: "monospace", fontStyle: "italic" }}>
                          ⚡ {leg.difficulty}
                        </div>
                      )}
                      {leg.reasoning && (
                        <div style={{ fontSize: 9, color: "#888", marginTop: 4, lineHeight: 1.4 }}>
                          {leg.reasoning}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        });
      })()}
    </div>
  );
}

function TierChip({ tier }) {
  const map = {
    lock:   { color: "#00ff87", label: "LOCK" },
    strong: { color: "#a3e635", label: "STRONG" },
    dog:    { color: "#a78bfa", label: "DOG" },
    lean:   { color: "#ffd700", label: "LEAN" },
    skip:   { color: "#555",    label: "PASS" },
  };
  const c = map[tier] || map.skip;
  return (
    <span style={{
      background: c.color + "18", color: c.color, border: `1px solid ${c.color}40`,
      fontSize: 8, fontFamily: "monospace", letterSpacing: 1.5,
      padding: "2px 6px", borderRadius: 3, fontWeight: 700,
    }}>{c.label}</span>
  );
}

// ── Hero pick: today's biggest single mispricing ─────────────────────────────
function HeroPickCard({ aiPicks }) {
  const bep = aiPicks?.best_edge_parlay;
  if (!bep || !bep.legs || bep.legs.length === 0) return null;
  const leg = bep.legs[0];
  const e = leg.edge || {};
  if (e.tier === "UNPRICED" || e.edge_pct == null) return null;

  const tierColor = e.color || "#fbbf24";
  const evPct = e.edge_pct;
  const ourProb = e.our_prob != null ? (e.our_prob * 100).toFixed(1) : null;
  const fairOdds = e.our_fair_odds;

  const { addLeg, isInSlip } = useBetSlip();
  const inSlip = isInSlip({ matchup: leg.matchup, play: leg.play, type: leg.type });

  return (
    <div style={{
      background: `linear-gradient(135deg, #050505, ${tierColor}10 60%, #050505)`,
      border: `2px solid ${tierColor}`,
      borderRadius: 12, padding: "22px 24px", marginBottom: 24,
      boxShadow: `0 0 40px ${tierColor}30`,
      position: "relative", overflow: "hidden",
    }}>
      <div style={{
        position: "absolute", top: 0, right: 0,
        background: tierColor, color: "#000",
        fontSize: 9, fontWeight: 900, letterSpacing: 2,
        padding: "4px 12px", borderBottomLeftRadius: 8,
      }}>
        {e.icon} BIGGEST MISPRICE
      </div>

      <div style={{ fontSize: 9, color: tierColor, letterSpacing: 3, fontWeight: 900, marginBottom: 4 }}>
        🎯 TODAY'S SHARPEST EDGE
      </div>
      <div style={{ fontSize: 10, color: "#666", marginBottom: 14 }}>
        Single biggest gap between book and model on the slate
      </div>

      <div style={{ fontSize: 28, color: "#fff", fontWeight: 900, lineHeight: 1.1, marginBottom: 6 }}>
        {leg.play}
      </div>
      <div style={{ fontSize: 12, color: "#888", fontFamily: "monospace", marginBottom: 16 }}>
        {leg.matchup}
      </div>

      {/* Big numbers row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, marginBottom: 16 }}>
        <div style={{ background: "#0a0a0a", borderRadius: 6, padding: "10px 12px", border: "1px solid #1a1a1a" }}>
          <div style={{ fontSize: 8, color: "#444", letterSpacing: 1.5, marginBottom: 4 }}>BOOK</div>
          <div style={{ fontSize: 18, color: "#fbbf24", fontWeight: 900, fontFamily: "monospace", lineHeight: 1 }}>
            {leg.odds >= 0 ? `+${leg.odds}` : leg.odds}
          </div>
        </div>
        <div style={{ background: "#0a0a0a", borderRadius: 6, padding: "10px 12px", border: `1px solid ${tierColor}30` }}>
          <div style={{ fontSize: 8, color: "#444", letterSpacing: 1.5, marginBottom: 4 }}>OUR FAIR</div>
          <div style={{ fontSize: 18, color: tierColor, fontWeight: 900, fontFamily: "monospace", lineHeight: 1 }}>
            {fairOdds != null ? (fairOdds >= 0 ? `+${fairOdds}` : fairOdds) : "—"}
          </div>
        </div>
        <div style={{ background: "#0a0a0a", borderRadius: 6, padding: "10px 12px", border: `1px solid ${tierColor}40` }}>
          <div style={{ fontSize: 8, color: "#444", letterSpacing: 1.5, marginBottom: 4 }}>EV %</div>
          <div style={{ fontSize: 18, color: tierColor, fontWeight: 900, fontFamily: "monospace", lineHeight: 1 }}>
            {evPct >= 0 ? `+${evPct}` : evPct}%
          </div>
        </div>
      </div>

      {/* Plain-English explainer */}
      <div style={{
        fontSize: 11, color: "#bbb", lineHeight: 1.6,
        padding: "12px 14px", background: "#0a0a0a", border: "1px solid #1a1a1a",
        borderRadius: 6, marginBottom: 14,
      }}>
        Book has it at <strong style={{ color: "#fbbf24" }}>{leg.odds >= 0 ? `+${leg.odds}` : leg.odds}</strong> ({(((leg.odds >= 0 ? 100 / (leg.odds + 100) : Math.abs(leg.odds) / (Math.abs(leg.odds) + 100))) * 100).toFixed(1)}% implied).
        Our model gives this <strong style={{ color: tierColor }}>{ourProb}%</strong> to hit.
        That's a <strong style={{ color: tierColor }}>{evPct >= 0 ? `+${evPct}` : evPct}% expected return</strong> per dollar — the sharpest gap on the slate.
        {leg.reasoning && <span style={{ display: "block", marginTop: 8, color: "#888", fontStyle: "italic", fontSize: 10 }}>{leg.reasoning}</span>}
      </div>

      <button onClick={() => addLeg({ ...leg, source: "Today's Sharpest" })} style={{
        width: "100%", padding: "12px",
        background: inSlip ? "#1a1a1a" : tierColor,
        color: inSlip ? tierColor : "#000",
        border: `2px solid ${tierColor}`,
        borderRadius: 8, fontSize: 12, fontWeight: 900,
        fontFamily: "monospace", letterSpacing: 2, cursor: "pointer",
        boxShadow: inSlip ? "none" : `0 4px 16px ${tierColor}50`,
        transition: "all 0.15s",
      }}>
        {inSlip ? "✓ ON YOUR SLIP" : "+ ADD TO SLIP"}
      </button>
    </div>
  );
}

// ── TRACK tab — full results log + CLV (the only metric that matters) ────────
function TrackBoard({ games }) {
  const { placed, updateStatus, removePlaced, clearAllPlaced, captureClosings } = usePlaced();

  // Auto-capture closing lines whenever the slate updates
  useEffect(() => { captureClosings(games); }, [games]);

  const settled = placed.filter(b => b.status === "WON" || b.status === "LOST");
  const wins = settled.filter(b => b.status === "WON").length;
  const losses = settled.filter(b => b.status === "LOST").length;
  const pending = placed.filter(b => b.status === "PENDING").length;

  let units = 0, totalWagered = 0;
  for (const b of settled) {
    const dec = parlayOdds(b.legs);
    const u = b.wager / 100;
    totalWagered += u;
    if (b.status === "WON") units += u * (dec - 1);
    else if (b.status === "LOST") units -= u;
  }
  const roi = totalWagered > 0 ? (units / totalWagered) * 100 : null;
  const winPct = settled.length > 0 ? Math.round((wins / settled.length) * 100) : null;

  // CLV across every leg we could measure
  let clvBeat = 0, clvTotal = 0, clvSum = 0, clvPctCount = 0;
  for (const b of placed) {
    for (const leg of b.legs) {
      const c = legCLV(leg);
      if (!c || c.beat == null) continue;
      clvTotal += 1;
      if (c.beat) clvBeat += 1;
      if (c.pct != null) { clvSum += c.pct; clvPctCount += 1; }
    }
  }
  const clvBeatRate = clvTotal > 0 ? Math.round((clvBeat / clvTotal) * 100) : null;
  const clvAvg = clvPctCount > 0 ? (clvSum / clvPctCount) : null;

  const unitsColor = units > 0 ? "#00ff87" : units < 0 ? "#ff3b3b" : "#888";
  const clvColor = clvBeatRate == null ? "#666" : clvBeatRate >= 55 ? "#00ff87" : clvBeatRate >= 50 ? "#fbbf24" : "#ff3b3b";

  const Stat = ({ label, value, sub, color = "#fff" }) => (
    <div style={{ background: "#0a0a0a", border: "1px solid #1a1a1a", borderRadius: 8, padding: "14px 12px", textAlign: "center" }}>
      <div style={{ fontSize: 8, color: "#444", letterSpacing: 2, marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 900, fontFamily: "monospace", color, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 8, color: "#444", marginTop: 4 }}>{sub}</div>}
    </div>
  );

  return (
    <div style={{ paddingBottom: 20 }}>
      <div style={{
        background: "linear-gradient(135deg, #0a0a0a, #0d1a14 80%, #0a0a0a)",
        border: "2px solid #00ff8730", borderRadius: 10,
        padding: "18px 20px", marginBottom: 16,
      }}>
        <div style={{ fontSize: 12, color: "#00ff87", letterSpacing: 3, fontWeight: 900 }}>
          📒 TRACK RECORD
        </div>
        <div style={{ fontSize: 9, color: "#666", marginTop: 4, lineHeight: 1.5 }}>
          Every bet you place is logged here. <strong style={{ color: "#888" }}>CLV (Closing Line Value)</strong> is
          the only proven predictor of long-term profit — if you consistently beat the closing line, you win over time.
        </div>
      </div>

      {placed.length === 0 ? (
        <div style={{
          background: "#0a0a0a", border: "1px dashed #1a1a1a",
          borderRadius: 8, padding: "40px 20px", textAlign: "center",
        }}>
          <div style={{ fontSize: 36, marginBottom: 12, opacity: 0.3 }}>📒</div>
          <div style={{ fontSize: 12, color: "#666", fontWeight: 700, letterSpacing: 1.5, marginBottom: 8 }}>
            NO BETS LOGGED YET
          </div>
          <div style={{ fontSize: 10, color: "#444", lineHeight: 1.6, maxWidth: 320, margin: "0 auto" }}>
            Build a slip from any pick, open the 🎟️ slip drawer, set a wager, and tap
            <strong style={{ color: "#00ff87" }}> PLACE BET</strong>.
            It lands here with the price you took — CLV gets measured automatically once the line closes.
          </div>
        </div>
      ) : (
        <>
          {/* Stat grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10, marginBottom: 12 }}>
            <Stat label="RECORD" value={`${wins}-${losses}`} sub={winPct != null ? `${winPct}% win` : `${pending} pending`} />
            <Stat label="UNITS" value={`${units >= 0 ? "+" : ""}${units.toFixed(2)}u`} color={unitsColor} sub={roi != null ? `${roi >= 0 ? "+" : ""}${roi.toFixed(1)}% ROI` : "—"} />
            <Stat label="BEAT THE CLOSE" value={clvBeatRate != null ? `${clvBeatRate}%` : "—"} color={clvColor} sub={`${clvBeat}/${clvTotal} legs`} />
            <Stat label="AVG CLV" value={clvAvg != null ? `${clvAvg >= 0 ? "+" : ""}${clvAvg.toFixed(2)}%` : "—"} color={clvColor} sub="ML legs only" />
          </div>

          {/* CLV verdict */}
          {clvBeatRate != null && clvTotal >= 5 && (
            <div style={{
              fontSize: 10, lineHeight: 1.5, padding: "10px 14px", marginBottom: 16,
              background: clvColor + "10", border: `1px solid ${clvColor}30`, borderRadius: 6,
              color: clvColor,
            }}>
              {clvBeatRate >= 55
                ? `✓ You're beating the close ${clvBeatRate}% of the time. That's the signature of a profitable bettor — keep doing exactly this.`
                : clvBeatRate >= 50
                ? `~ You're roughly even with the close (${clvBeatRate}%). Not losing to the market, but not beating it yet. Need a real edge to profit after vig.`
                : `✗ You're getting worse prices than the close (${clvBeatRate}%). Long-term this loses money regardless of short-term W/L. The picks aren't finding value.`}
              {clvTotal < 20 && <span style={{ color: "#666", display: "block", marginTop: 4 }}>Sample still small ({clvTotal} legs) — needs ~30+ to trust.</span>}
            </div>
          )}

          {/* Bet log */}
          <div style={{ fontSize: 9, color: "#444", letterSpacing: 2, marginBottom: 8 }}>BET LOG</div>
          {placed.map(b => {
            const dec = parlayOdds(b.legs);
            const pay = b.wager * dec;
            const sc = b.status === "WON" ? "#00ff87" : b.status === "LOST" ? "#ff3b3b" : b.status === "PUSH" ? "#888" : "#fbbf24";
            const d = new Date(b.placedAt).toLocaleDateString("en-CA", { timeZone: "America/Los_Angeles" });
            const t = new Date(b.placedAt).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/Los_Angeles" });
            return (
              <div key={b.id} style={{
                background: "#0a0a0a", border: `1px solid ${sc}40`,
                borderRadius: 8, padding: "12px 14px", marginBottom: 8,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <div style={{ fontSize: 8, color: "#444", letterSpacing: 1 }}>
                    {d} {t} PT · {b.legs.length}-LEG · ${b.wager} → ${pay.toFixed(2)}
                  </div>
                  <span style={{
                    fontSize: 9, fontWeight: 900, letterSpacing: 1, color: sc,
                    background: sc + "18", border: `1px solid ${sc}50`,
                    padding: "1px 7px", borderRadius: 3,
                  }}>{b.status}</span>
                </div>
                {b.legs.map((leg, i) => {
                  const clv = legCLV(leg);
                  const cc = clv?.beat == null ? "#666" : clv.beat ? "#00ff87" : "#ff3b3b";
                  return (
                    <div key={i} style={{ marginBottom: 6, paddingBottom: 6, borderBottom: i < b.legs.length - 1 ? "1px solid #141414" : "none" }}>
                      <div style={{ fontSize: 11, color: "#ddd" }}>
                        <span style={{ color: "#555" }}>#{i + 1} </span>{leg.play}
                        <span style={{ color: "#fbbf24", marginLeft: 6, fontFamily: "monospace" }}>
                          {leg.odds >= 0 ? `+${leg.odds}` : leg.odds}
                        </span>
                      </div>
                      <div style={{ fontSize: 8, color: "#444", marginLeft: 14 }}>{leg.matchup}</div>
                      {clv ? (
                        <div style={{ fontSize: 9, color: cc, marginLeft: 14, marginTop: 2, fontFamily: "monospace" }}>
                          {clv.beat == null ? "◦" : clv.beat ? "✓ BEAT CLOSE" : "✗ LOST CLV"}
                          {clv.pct != null && ` ${clv.pct >= 0 ? "+" : ""}${clv.pct.toFixed(2)}%`}
                          <span style={{ color: "#444", marginLeft: 6 }}>· {clv.label}</span>
                        </div>
                      ) : (
                        <div style={{ fontSize: 8, color: "#333", marginLeft: 14, marginTop: 2 }}>
                          CLV pending — captured once the line closes
                        </div>
                      )}
                    </div>
                  );
                })}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
                  {b.status === "PENDING" ? (
                    <div style={{ display: "flex", gap: 5 }}>
                      <button onClick={() => updateStatus(b.id, "WON")} style={{ background: "#00ff8718", color: "#00ff87", border: "1px solid #00ff8750", borderRadius: 4, fontSize: 9, fontWeight: 800, padding: "4px 12px", cursor: "pointer", fontFamily: "monospace" }}>✓ WON</button>
                      <button onClick={() => updateStatus(b.id, "LOST")} style={{ background: "#ff3b3b18", color: "#ff3b3b", border: "1px solid #ff3b3b50", borderRadius: 4, fontSize: 9, fontWeight: 800, padding: "4px 12px", cursor: "pointer", fontFamily: "monospace" }}>✗ LOST</button>
                      <button onClick={() => updateStatus(b.id, "PUSH")} style={{ background: "#88888818", color: "#888", border: "1px solid #88888850", borderRadius: 4, fontSize: 9, fontWeight: 800, padding: "4px 12px", cursor: "pointer", fontFamily: "monospace" }}>= PUSH</button>
                    </div>
                  ) : (
                    <button onClick={() => updateStatus(b.id, "PENDING")} style={{ background: "transparent", color: "#444", border: "1px solid #1a1a1a", borderRadius: 4, fontSize: 8, padding: "3px 10px", cursor: "pointer", fontFamily: "monospace" }}>UNDO</button>
                  )}
                  <button onClick={() => removePlaced(b.id)} style={{ background: "transparent", border: "none", color: "#333", fontSize: 15, cursor: "pointer" }}>×</button>
                </div>
              </div>
            );
          })}
          <button onClick={() => { if (confirm("Wipe the entire track record? This cannot be undone.")) clearAllPlaced(); }} style={{
            width: "100%", marginTop: 8, background: "transparent",
            border: "1px solid #1a1a1a", color: "#444",
            fontSize: 9, fontFamily: "monospace", letterSpacing: 1.5,
            padding: "10px", borderRadius: 6, cursor: "pointer",
          }}>RESET TRACK RECORD</button>
        </>
      )}
    </div>
  );
}

// ── Why-this-pick expander — small "+" button reveals reasons ────────────────
function WhyExpander({ reasons, color = "#00ff87" }) {
  const [open, setOpen] = useState(false);
  if (!reasons || reasons.length === 0) return null;
  return (
    <div style={{ marginTop: 6 }}>
      <button onClick={() => setOpen(o => !o)} style={{
        background: "transparent", border: "none", padding: 0,
        color: color, fontSize: 9, fontFamily: "monospace",
        letterSpacing: 1.5, cursor: "pointer", fontWeight: 700,
        opacity: 0.7,
      }}>
        {open ? "▼ HIDE WHY" : "▶ WHY THIS PICK"}
      </button>
      {open && (
        <div style={{
          marginTop: 6, padding: "8px 10px",
          background: `${color}06`, border: `1px solid ${color}25`,
          borderRadius: 4,
        }}>
          {reasons.map((r, j) => (
            <div key={j} style={{ fontSize: 10, color: "#aaa", marginBottom: 3, lineHeight: 1.5 }}>
              • {r}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── THE FORMULA — self-contained correlated parlay (the flagship) ───────────
function FormulaParlayCard({ parlay }) {
  const { addLeg, isInSlip } = useBetSlip();
  if (!parlay) return null;
  const games = parlay.games || [];
  const hasGames = games.length > 0;
  const GOLD = "#f5d020";

  const addGame = (g) => g.legs.forEach(l => addLeg({ ...l, source: "The Formula" }));

  return (
    <div style={{
      background: hasGames
        ? `linear-gradient(135deg, #0a0a05, ${GOLD}0d 50%, #0a0a05)`
        : "#0a0a0a",
      border: `2px solid ${hasGames ? GOLD : "#2a2510"}`,
      borderRadius: 12, padding: "20px 22px", marginBottom: 24,
      boxShadow: hasGames ? `0 0 44px ${GOLD}25` : "none",
      position: "relative", overflow: "hidden",
    }}>
      <div style={{
        position: "absolute", top: 0, right: 0,
        background: hasGames ? GOLD : "#2a2510", color: "#000",
        fontSize: 8, fontWeight: 900, letterSpacing: 2,
        padding: "4px 12px", borderBottomLeftRadius: 8,
      }}>
        ⭐ THE ONE
      </div>

      <div style={{ fontSize: 13, color: hasGames ? GOLD : "#555", letterSpacing: 3, fontWeight: 900 }}>
        🎯 THE FORMULA
      </div>
      <div style={{ fontSize: 9, color: "#888", marginTop: 4, lineHeight: 1.5 }}>
        Self-contained correlated parlay — each game stacks <strong style={{ color: "#aaa" }}>UNDER + Favorite ML + F5 UNDER</strong>.
        One thesis, three expressions: <em>a low-scoring game the better team controls early.</em>
      </div>

      {!hasGames && (
        <div style={{
          marginTop: 16, padding: "20px 16px", textAlign: "center",
          background: "#080808", border: "1px dashed #2a2510", borderRadius: 8,
          fontSize: 10, color: "#666", lineHeight: 1.6,
        }}>
          {parlay.note || "No games clear all three filters today."}
          <div style={{ fontSize: 9, color: "#444", marginTop: 8 }}>
            The Formula only fires when the script lines up. Discipline &gt; forcing a play.
          </div>
        </div>
      )}

      {hasGames && (
        <>
          {/* Honest probability story */}
          <div style={{
            display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8,
            margin: "16px 0",
          }}>
            {[
              { label: "BOOK IMPLIED", val: parlay.book_implied_pct, color: "#fb7185", sub: "what they price" },
              { label: "INDEPENDENT", val: parlay.joint_naive_pct, color: "#fbbf24", sub: "model, no corr" },
              { label: "CORRELATED", val: parlay.joint_corr_pct, color: GOLD, sub: "the real read" },
            ].map(({ label, val, color, sub }) => (
              <div key={label} style={{
                background: "#080808", border: `1px solid ${color}30`,
                borderRadius: 6, padding: "10px 8px", textAlign: "center",
              }}>
                <div style={{ fontSize: 7, color: "#444", letterSpacing: 1.5, marginBottom: 4 }}>{label}</div>
                <div style={{ fontSize: 17, color, fontWeight: 900, fontFamily: "monospace", lineHeight: 1 }}>
                  {val != null ? `${val}%` : "—"}
                </div>
                <div style={{ fontSize: 7, color: "#444", marginTop: 3 }}>{sub}</div>
              </div>
            ))}
          </div>
          <div style={{
            fontSize: 9, color: "#aaa", lineHeight: 1.5, marginBottom: 16,
            padding: "8px 12px", background: `${GOLD}0a`, border: `1px solid ${GOLD}25`, borderRadius: 5,
          }}>
            The book prices these 3 legs <strong>independent</strong>. They're not — they win and lose together.
            The gap between <strong style={{ color: "#fb7185" }}>{parlay.book_implied_pct}%</strong> (book) and
            <strong style={{ color: GOLD }}> {parlay.joint_corr_pct}%</strong> (correlation-adjusted) is the entire thesis.
          </div>

          {/* Per-game correlated clusters */}
          {games.map((g, gi) => (
            <div key={gi} style={{
              border: `1px solid ${GOLD}30`, borderRadius: 8,
              padding: "12px 14px", marginBottom: 10,
              background: "#080808",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8, flexWrap: "wrap", gap: 6 }}>
                <div style={{ fontSize: 12, color: "#fff", fontWeight: 800 }}>
                  <span style={{ color: GOLD }}>#{gi + 1}</span> {g.matchup}
                </div>
                <div style={{ fontSize: 8, color: "#666", fontFamily: "monospace" }}>
                  U:{g.under_score} · F5:{g.f5_score} · {g.ctrl_role === "DOG +1.5" ? "Dog" : "Fav"}:{g.ctrl_score}
                </div>
              </div>

              {/* The 3 correlated legs, bracketed */}
              <div style={{ borderLeft: `2px solid ${GOLD}50`, paddingLeft: 10 }}>
                {g.legs.map((leg, li) => {
                  const e = leg.edge || {};
                  const inSlip = isInSlip({ matchup: leg.matchup, play: leg.play, type: leg.type });
                  return (
                    <div key={li} style={{
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "6px 0",
                      borderBottom: li < 2 ? "1px solid #141414" : "none",
                    }}>
                      <span style={{ fontSize: 7, color: GOLD, fontWeight: 700, letterSpacing: 1, minWidth: 64 }}>
                        {leg.leg_role}
                      </span>
                      <span style={{ fontSize: 12, color: "#fff", fontWeight: 700, flex: 1, minWidth: 0 }}>
                        {leg.play}
                      </span>
                      <span style={{ fontSize: 11, color: "#fbbf24", fontFamily: "monospace", fontWeight: 700 }}>
                        {leg.odds >= 0 ? `+${leg.odds}` : leg.odds}
                      </span>
                      {e.tier && e.tier !== "UNPRICED" && (
                        <span style={{
                          fontSize: 8, color: e.color, background: e.color + "18",
                          border: `1px solid ${e.color}50`, padding: "1px 5px",
                          borderRadius: 3, fontWeight: 800, fontFamily: "monospace",
                        }}>
                          {e.icon} {e.edge_pct >= 0 ? "+" : ""}{e.edge_pct}%
                        </span>
                      )}
                      <button onClick={() => addLeg({ ...leg, source: "The Formula" })} style={{
                        background: inSlip ? GOLD : `${GOLD}18`,
                        border: `1px solid ${inSlip ? GOLD : GOLD + "60"}`,
                        color: inSlip ? "#000" : GOLD,
                        fontSize: 8, fontWeight: 800, fontFamily: "monospace",
                        padding: "2px 7px", borderRadius: 10, cursor: "pointer",
                      }}>
                        {inSlip ? "✓" : "+"}
                      </button>
                    </div>
                  );
                })}
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
                <div style={{ fontSize: 9, color: "#888", fontFamily: "monospace" }}>
                  indep <span style={{ color: "#fbbf24" }}>{g.naive_triple_pct}%</span>
                  <span style={{ color: "#444" }}> → </span>
                  correlated <span style={{ color: GOLD, fontWeight: 700 }}>{g.corr_triple_pct}%</span>
                </div>
                <button onClick={() => addGame(g)} style={{
                  background: "transparent", border: `1px solid ${GOLD}50`,
                  color: GOLD, fontSize: 8, fontWeight: 800, fontFamily: "monospace",
                  letterSpacing: 1, padding: "4px 10px", borderRadius: 4, cursor: "pointer",
                }}>
                  + ADD ALL 3
                </button>
              </div>
            </div>
          ))}

          {/* Combined */}
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            marginTop: 14, padding: "12px 14px",
            background: `${GOLD}0d`, border: `1px solid ${GOLD}40`, borderRadius: 8,
          }}>
            <div>
              <div style={{ fontSize: 8, color: "#666", letterSpacing: 1.5 }}>FULL TICKET</div>
              <div style={{ fontSize: 22, color: GOLD, fontWeight: 900, fontFamily: "monospace" }}>
                {parlay.combined_odds}
              </div>
              <div style={{ fontSize: 8, color: "#666", fontFamily: "monospace" }}>
                ${parlay.payout_per_100?.toLocaleString()}/$100
              </div>
            </div>
            <button onClick={() => games.forEach(addGame)} style={{
              background: GOLD, color: "#000", border: "none",
              borderRadius: 8, padding: "12px 20px",
              fontSize: 11, fontWeight: 900, fontFamily: "monospace",
              letterSpacing: 1.5, cursor: "pointer",
              boxShadow: `0 4px 16px ${GOLD}50`,
            }}>
              + ADD FULL FORMULA
            </button>
          </div>

          <div style={{ fontSize: 8, color: "#555", marginTop: 10, lineHeight: 1.5, fontStyle: "italic" }}>
            {parlay.note}
          </div>
        </>
      )}
    </div>
  );
}

// ── Sharp Money Parlay — every leg is here because the LINE moved ───────────
function SharpParlayCard({ parlay }) {
  if (!parlay) return null;
  const legs = parlay.legs || [];
  const hasLegs = legs.length > 0;
  const accent = "#fbbf24";

  // Always show 4 slots
  const SLOTS = [1, 2, 3, 4].map((n, i) => legs[i] ? legs[i] : { _tbd: true, rank: n });

  const labelColor = (label) =>
    label === "STEAM" ? "#fb7185"
    : label === "SHARP" ? "#fbbf24"
    : "#a78bfa";

  return (
    <div style={{
      background: "linear-gradient(135deg, #0a0a0a, #1a1100 60%, #0a0a0a)",
      border: `2px solid ${hasLegs ? accent : "#2a2000"}`, borderRadius: 10,
      padding: "18px 20px", marginBottom: 24,
      boxShadow: hasLegs ? `0 0 32px ${accent}30` : "none",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: hasLegs ? accent : "#555", letterSpacing: 3, fontWeight: 900 }}>
            💰 SHARP MONEY PARLAY
          </div>
          <div style={{ fontSize: 9, color: "#666", marginTop: 4 }}>
            Pure follow-the-line — every leg picked because sharps already moved the price
          </div>
          {parlay.note && !hasLegs && (
            <div style={{ fontSize: 8, color: "#444", marginTop: 6, fontStyle: "italic" }}>
              {parlay.note}
            </div>
          )}
        </div>
        {hasLegs && (
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 26, color: accent, fontWeight: 900, fontFamily: "monospace", textShadow: `0 0 12px ${accent}50` }}>
              {parlay.combined_odds}
            </div>
            <div style={{ fontSize: 9, color: "#666", fontFamily: "monospace" }}>
              ${parlay.payout_per_100?.toLocaleString()}/$100
            </div>
          </div>
        )}
      </div>

      {/* Banner */}
      {hasLegs && (
        <div style={{
          fontSize: 9, color: "#fde68a", marginBottom: 10, lineHeight: 1.5,
          padding: "8px 12px", background: `${accent}10`, borderRadius: 4,
          border: `1px solid ${accent}30`,
        }}>
          ⚡ <strong>FADE THE PUBLIC, FOLLOW THE MONEY</strong> — every leg here is on a side
          where the sportsbooks moved the line in response to professional bettors. No model overlay,
          no public consensus — just pure line-movement signal.
        </div>
      )}

      {/* Legs */}
      {SLOTS.map((leg, i) => {
        const isUnder = leg.type?.includes("UNDER");
        const isOver = leg.type?.includes("OVER");
        const isML = leg.type === "SHARP_ML";
        const legColor = leg._tbd ? "#333"
          : isUnder ? "#00ff87"
          : isOver ? "#fbbf24"
          : "#a78bfa";
        const rank = leg.rank || (i + 1);
        const rlColor = leg._tbd ? "#333" : labelColor(leg.rank_label);

        return (
          <div key={i} style={{
            borderTop: "1px solid #1a1a1a",
            padding: "13px 0",
            display: "flex", gap: 12, alignItems: "flex-start",
            background: leg._tbd ? "#ffffff03" : `${legColor}07`,
            borderLeft: `2px solid ${leg._tbd ? "#333" : legColor + "40"}`,
            paddingLeft: 10, borderRadius: "0 4px 4px 0", marginBottom: 2,
            opacity: leg._tbd ? 0.4 : 1,
          }}>
            <div style={{ flexShrink: 0, textAlign: "center", minWidth: 40 }}>
              <div style={{
                width: 32, height: 32, borderRadius: "50%",
                background: legColor + "20", color: legColor,
                border: `2px solid ${legColor}60`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 13, fontWeight: 900, margin: "0 auto",
              }}>#{rank}</div>
              {!leg._tbd && (
                <div style={{
                  fontSize: 7, color: rlColor, marginTop: 4,
                  fontFamily: "monospace", letterSpacing: 0.5, fontWeight: 700,
                }}>
                  ⚡ {leg.rank_label}
                </div>
              )}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              {leg._tbd ? (
                <div style={{ fontSize: 12, color: "#555", fontFamily: "monospace", letterSpacing: 2, paddingTop: 6 }}>
                  ⏳ AWAITING MOVEMENT — UPDATES AS LINES SHIFT
                </div>
              ) : (
                <>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 13, color: legColor, fontWeight: 700 }}>{leg.play}</span>
                    {leg.odds != null && (
                      <span style={{ fontSize: 10, color: "#fbbf24", fontFamily: "monospace", fontWeight: 700 }}>
                        {leg.odds >= 0 ? `+${leg.odds}` : leg.odds}
                      </span>
                    )}
                    <AddPill leg={leg} source="Sharp Money" accentColor={legColor} />
                  </div>
                  <div style={{ fontSize: 10, color: "#666", marginTop: 2, fontFamily: "monospace" }}>
                    {leg.matchup}
                  </div>
                  {leg.movement_text && (
                    <div style={{ fontSize: 9, color: legColor, marginTop: 4, fontFamily: "monospace", letterSpacing: 0.5 }}>
                      📈 {leg.movement_text}
                    </div>
                  )}
                  {leg.reasoning && (
                    <div style={{ fontSize: 9, color: "#999", marginTop: 3, lineHeight: 1.4, fontStyle: "italic" }}>
                      {leg.reasoning}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Line movement strip (sharp-money tells per game) ────────────────────────
function LineMovementStrip({
  openTotal, curTotal, totalMv,
  openAML, curAML, awayMv,
  openHML, curHML, homeMv,
  awayTeam, homeTeam,
}) {
  const fmtML = (v) => v == null ? "—" : (v >= 0 ? `+${v}` : `${v}`);
  const fmtMv = (v) => {
    if (v == null || v === 0) return null;
    return v > 0 ? `↑${Math.abs(v)}` : `↓${Math.abs(v)}`;
  };

  const totalSig = totalMv == null || Math.abs(totalMv) < 0.5
    ? null
    : totalMv < 0 ? { text: "SHARP UNDER", color: "#00ff87" }
                  : { text: "SHARP OVER",  color: "#fbbf24" };

  const awaySig = awayMv == null || Math.abs(awayMv) < 8
    ? null
    : awayMv > 0 ? { text: `${awayTeam} drift`, color: "#666" }
                 : { text: `${awayTeam} steam`, color: "#00ff87" };
  const homeSig = homeMv == null || Math.abs(homeMv) < 8
    ? null
    : homeMv > 0 ? { text: `${homeTeam} drift`, color: "#666" }
                 : { text: `${homeTeam} steam`, color: "#00ff87" };

  // Nothing tracked yet
  if (openTotal == null && openAML == null && openHML == null) {
    return (
      <div style={{
        fontSize: 8, color: "#333", letterSpacing: 1.2,
        padding: "4px 0 8px", borderBottom: "1px dashed #1a1a1a", marginBottom: 8,
      }}>
        ⏳ TRACKING OPENING LINE — sharp-money movement will show after a few hours
      </div>
    );
  }

  return (
    <div style={{
      display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center",
      fontSize: 9, color: "#666", fontFamily: "monospace",
      padding: "6px 0 8px", borderBottom: "1px dashed #1a1a1a", marginBottom: 8,
    }}>
      {/* Total movement */}
      {openTotal != null && curTotal != null && (
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ color: "#444" }}>O/U:</span>
          <span>{openTotal}</span>
          <span style={{ color: "#333" }}>→</span>
          <span style={{ color: "#fff" }}>{curTotal}</span>
          {fmtMv(totalMv) && (
            <span style={{ color: totalMv < 0 ? "#00ff87" : "#fbbf24", fontWeight: 800 }}>
              {fmtMv(totalMv)}
            </span>
          )}
          {totalSig && (
            <span style={{
              color: totalSig.color, background: totalSig.color + "18",
              border: `1px solid ${totalSig.color}50`,
              padding: "1px 5px", borderRadius: 3, fontWeight: 800, letterSpacing: 0.5,
            }}>⚡ {totalSig.text}</span>
          )}
        </div>
      )}

      {/* ML movement */}
      {openAML != null && curAML != null && awayMv !== 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ color: "#444" }}>{awayTeam}:</span>
          <span>{fmtML(openAML)}</span>
          <span style={{ color: "#333" }}>→</span>
          <span style={{ color: "#fff" }}>{fmtML(curAML)}</span>
          {fmtMv(awayMv) && (
            <span style={{ color: awayMv < 0 ? "#00ff87" : "#fb7185", fontWeight: 700 }}>
              {fmtMv(awayMv)}
            </span>
          )}
        </div>
      )}
      {openHML != null && curHML != null && homeMv !== 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ color: "#444" }}>{homeTeam}:</span>
          <span>{fmtML(openHML)}</span>
          <span style={{ color: "#333" }}>→</span>
          <span style={{ color: "#fff" }}>{fmtML(curHML)}</span>
          {fmtMv(homeMv) && (
            <span style={{ color: homeMv < 0 ? "#00ff87" : "#fb7185", fontWeight: 700 }}>
              {fmtMv(homeMv)}
            </span>
          )}
        </div>
      )}

      {/* All quiet */}
      {totalMv === 0 && awayMv === 0 && homeMv === 0 && (
        <span style={{ color: "#333" }}>NO MOVEMENT YET</span>
      )}
    </div>
  );
}

// ── Line Movement Board — every game with movement, sorted by magnitude ─────
function LineMovementBoard({ games }) {
  const eligible = (games || [])
    .filter(g => g.abstract_state === "Preview")
    .map(g => {
      const lm = g.line_movement || {};
      const ml = g.moneyline_data || {};
      const tmv = lm.total_movement;
      const amv = ml.away_ml_movement;
      const hmv = ml.home_ml_movement;
      const magnitude = Math.max(
        tmv != null ? Math.abs(tmv) * 10 : 0,    // 1 run weighted as 10 ML cents
        amv != null ? Math.abs(amv) : 0,
        hmv != null ? Math.abs(hmv) : 0,
      );
      return { g, lm, ml, tmv, amv, hmv, magnitude };
    })
    .filter(x => x.magnitude > 0)
    .sort((a, b) => b.magnitude - a.magnitude);

  if (eligible.length === 0) return null;

  return (
    <div style={{
      background: "linear-gradient(135deg, #0a0a0a, #1a1400 80%, #0a0a0a)",
      border: "2px solid #fbbf2430", borderRadius: 10,
      padding: "16px 18px", marginBottom: 24,
    }}>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: "#fbbf24", letterSpacing: 3, fontWeight: 900 }}>
          📊 LINE MOVEMENT BOARD
        </div>
        <div style={{ fontSize: 9, color: "#666", marginTop: 3 }}>
          Where the lines have moved since opening · sharp-money tells · {eligible.length} games tracking
        </div>
      </div>
      {eligible.map(({ g, lm, ml, tmv, amv, hmv }) => {
        const totalSig = tmv != null && Math.abs(tmv) >= 0.5
          ? (tmv < 0 ? { txt: "⚡ SHARP UNDER", color: "#00ff87" }
                     : { txt: "⚡ SHARP OVER",  color: "#fbbf24" })
          : null;
        return (
          <div key={g.game_pk} style={{
            background: "#0a0a0a", border: "1px solid #1a1a1a",
            borderRadius: 6, padding: "10px 12px", marginBottom: 6,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontSize: 11, color: "#fff", fontWeight: 700 }}>
                {g.away_team} @ {g.home_team}
              </div>
              {totalSig && (
                <span style={{
                  fontSize: 9, color: totalSig.color, background: totalSig.color + "18",
                  border: `1px solid ${totalSig.color}50`,
                  padding: "2px 6px", borderRadius: 3, fontWeight: 800, letterSpacing: 0.5,
                  fontFamily: "monospace",
                }}>{totalSig.txt}</span>
              )}
            </div>
            <div style={{ fontSize: 9, color: "#666", marginTop: 4, fontFamily: "monospace", display: "flex", gap: 12, flexWrap: "wrap" }}>
              {tmv != null && tmv !== 0 && (
                <span>O/U: <span style={{ color: "#888" }}>{lm.opening_total}</span> → <span style={{ color: "#fff" }}>{lm.current_total ?? lm.closing_total}</span> <strong style={{ color: tmv < 0 ? "#00ff87" : "#fbbf24" }}>{tmv > 0 ? `↑${tmv}` : `↓${Math.abs(tmv)}`}</strong></span>
              )}
              {amv != null && amv !== 0 && (
                <span>{g.away_team_abbr || "AWAY"}: <span style={{ color: "#888" }}>{ml.opening_away_ml >= 0 ? `+${ml.opening_away_ml}` : ml.opening_away_ml}</span> → <span style={{ color: "#fff" }}>{(ml.current_away_ml ?? ml.closing_away_ml ?? ml.away_ml) >= 0 ? `+${ml.current_away_ml ?? ml.closing_away_ml ?? ml.away_ml}` : (ml.current_away_ml ?? ml.closing_away_ml ?? ml.away_ml)}</span> <strong style={{ color: amv < 0 ? "#00ff87" : "#fb7185" }}>{amv > 0 ? `↑${amv}` : `↓${Math.abs(amv)}`}</strong></span>
              )}
              {hmv != null && hmv !== 0 && (
                <span>{g.home_team_abbr || "HOME"}: <span style={{ color: "#888" }}>{ml.opening_home_ml >= 0 ? `+${ml.opening_home_ml}` : ml.opening_home_ml}</span> → <span style={{ color: "#fff" }}>{(ml.current_home_ml ?? ml.closing_home_ml ?? ml.home_ml) >= 0 ? `+${ml.current_home_ml ?? ml.closing_home_ml ?? ml.home_ml}` : (ml.current_home_ml ?? ml.closing_home_ml ?? ml.home_ml)}</span> <strong style={{ color: hmv < 0 ? "#00ff87" : "#fb7185" }}>{hmv > 0 ? `↑${hmv}` : `↓${Math.abs(hmv)}`}</strong></span>
              )}
            </div>
          </div>
        );
      })}
      <div style={{ fontSize: 8, color: "#333", marginTop: 8, fontStyle: "italic", letterSpacing: 0.5 }}>
        ↓ DOWN movement on a total = sharp UNDER · ↓ on ML = team improved · ↑ on ML = team got worse
      </div>
    </div>
  );
}

// ── ATS / Run Line section (favorites -1.5 + dogs +1.5) ─────────────────────
function RunLinePicks({ topFaves, topDogs }) {
  const ml_to_prob = (ml) => ml >= 0 ? 100 / (ml + 100) : Math.abs(ml) / (Math.abs(ml) + 100);
  const american_to_decimal = (ml) => ml >= 0 ? 1 + ml / 100 : 1 + 100 / Math.abs(ml);

  // Estimate fav -1.5 RL odds from ML (typical books shift ~+125-160)
  const estimateFavRL = (ml) => {
    if (ml == null) return null;
    const p = ml_to_prob(ml);
    const rlProb = Math.max(0.20, p - 0.18);    // -1.5 cuts ~18% off
    return rlProb >= 0.5 ? Math.round(-100 * rlProb / (1 - rlProb)) : Math.round(100 * (1 - rlProb) / rlProb);
  };
  const estimateDogRL = (ml) => {
    if (ml == null) return null;
    const p = ml_to_prob(ml);
    const rlProb = Math.min(0.92, p + 0.20);    // +1.5 adds ~20%
    return rlProb >= 0.5 ? Math.round(-100 * rlProb / (1 - rlProb)) : Math.round(100 * (1 - rlProb) / rlProb);
  };

  // Score each pick: edge of model_prob vs estimated RL odds
  const scoreFav = (f) => {
    const ml = f.moneyline;
    if (ml == null) return null;
    const baseProb = ml_to_prob(ml);
    const ourProb = Math.max(0.10, Math.min(0.65, baseProb - 0.18 + (f.fav_score - 50) * 0.0014));
    const rlOdds = estimateFavRL(ml);
    const dec = american_to_decimal(rlOdds);
    const ev = (ourProb * dec - 1) * 100;
    return { rlOdds, ev, ourProb };
  };
  const scoreDog = (d) => {
    const ml = d.moneyline;
    if (ml == null) return null;
    const winProb = ml_to_prob(ml);
    const ourProb = Math.max(0.50, Math.min(0.92, winProb + 0.20 + (d.dog_score - 50) * 0.0010));
    const rlOdds = estimateDogRL(ml);
    const dec = american_to_decimal(rlOdds);
    const ev = (ourProb * dec - 1) * 100;
    return { rlOdds, ev, ourProb };
  };

  const favLines = (topFaves || [])
    .map(f => ({ ...f, _ats: scoreFav(f), side: "fav" }))
    .filter(f => f._ats != null)
    .sort((a, b) => b._ats.ev - a._ats.ev);

  const dogLines = (topDogs || [])
    .map(d => ({ ...d, _ats: scoreDog(d), side: "dog" }))
    .filter(d => d._ats != null)
    .sort((a, b) => b._ats.ev - a._ats.ev);

  if (!favLines.length && !dogLines.length) return null;

  const tierFor = (ev) =>
    ev >= 8 ? { tier: "CRUSH", color: "#00ff87", icon: "💎" }
    : ev >= 3 ? { tier: "EDGE", color: "#a3e635", icon: "📈" }
    : ev >= 0 ? { tier: "FAIR", color: "#fbbf24", icon: "⚖️" }
    : { tier: "PASS", color: "#666", icon: "🚫" };

  const RLRow = ({ pick }) => {
    const ats = pick._ats;
    const t = tierFor(ats.ev);
    const isFav = pick.side === "fav";
    const team = isFav ? pick.fav_team : pick.dog_team;
    const play = `${team} ${isFav ? "-1.5" : "+1.5"} RL`;
    return (
      <div style={{
        background: "#0a0a0a", border: `1px solid ${t.color}30`,
        borderRadius: 8, padding: "12px 14px", marginBottom: 8,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <div>
            <div style={{ fontSize: 13, color: "#fff", fontWeight: 700 }}>
              {team} <span style={{ color: t.color, fontSize: 11 }}>{isFav ? "-1.5" : "+1.5"}</span>
            </div>
            <div style={{ fontSize: 9, color: "#666", marginTop: 2 }}>{pick.matchup}</div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span style={{ fontSize: 13, color: "#fbbf24", fontFamily: "monospace", fontWeight: 800 }}>
              {ats.rlOdds >= 0 ? `+${ats.rlOdds}` : ats.rlOdds}
            </span>
            <span style={{
              fontSize: 9, color: t.color, background: `${t.color}18`,
              border: `1px solid ${t.color}50`, padding: "2px 6px", borderRadius: 3,
              fontFamily: "monospace", fontWeight: 800, letterSpacing: 0.5,
            }}>
              {t.icon} {t.tier} {ats.ev >= 0 ? `+${ats.ev.toFixed(1)}` : ats.ev.toFixed(1)}%
            </span>
            <AddPill
              leg={{ matchup: pick.matchup, play, odds: ats.rlOdds, type: isFav ? "FAV_RL" : "DOG_RL" }}
              source="ATS / Run Line"
              accentColor={t.color}
            />
          </div>
        </div>
      </div>
    );
  };

  return (
    <div style={{
      background: "#080808", border: "1px solid #1a1a1a",
      borderRadius: 10, padding: "16px 18px", marginBottom: 24,
    }}>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: "#a3e635", letterSpacing: 3, fontWeight: 900 }}>
          📏 ATS / RUN LINE PLAYS
        </div>
        <div style={{ fontSize: 9, color: "#444", marginTop: 3 }}>
          Favorites covering -1.5 · dogs +1.5 cushion · ranked by estimated EV
        </div>
      </div>
      {favLines.length > 0 && (
        <>
          <div style={{ fontSize: 8, color: "#fb7185", letterSpacing: 2, fontWeight: 700, margin: "10px 0 6px" }}>
            ⭐ FAVORITES -1.5
          </div>
          {favLines.slice(0, 4).map((p, i) => <RLRow key={`f-${i}`} pick={p} />)}
        </>
      )}
      {dogLines.length > 0 && (
        <>
          <div style={{ fontSize: 8, color: "#a78bfa", letterSpacing: 2, fontWeight: 700, margin: "12px 0 6px" }}>
            🐕 DOGS +1.5
          </div>
          {dogLines.slice(0, 4).map((p, i) => <RLRow key={`d-${i}`} pick={p} />)}
        </>
      )}
    </div>
  );
}

// ── Bet Builder — game-by-game ML/RL/Total tap-to-add ────────────────────────
function BetBuilder({ games }) {
  const eligible = (games || []).filter(g => {
    const ml = g.moneyline_data || {};
    const lm = g.line_movement || {};
    const hasML = (ml.closing_away_ml ?? ml.away_ml) != null && (ml.closing_home_ml ?? ml.home_ml) != null;
    const hasTotal = (lm.closing_total ?? lm.current_total) != null;
    return g.abstract_state === "Preview" && (hasML || hasTotal);
  });

  if (eligible.length === 0) return null;

  // Estimate RL odds from ML (same heuristic as RunLinePicks)
  const ml_to_prob = (ml) => ml >= 0 ? 100 / (ml + 100) : Math.abs(ml) / (Math.abs(ml) + 100);
  const probToAmerican = (p) => p >= 0.5 ? Math.round(-100 * p / (1 - p)) : Math.round(100 * (1 - p) / p);
  const favRL = (ml) => probToAmerican(Math.max(0.20, ml_to_prob(ml) - 0.18));
  const dogRL = (ml) => probToAmerican(Math.min(0.92, ml_to_prob(ml) + 0.20));

  return (
    <div style={{
      background: "linear-gradient(135deg, #0a0a0a, #001a14 80%, #0a0a0a)",
      border: "2px solid #00ff8730", borderRadius: 10,
      padding: "18px 20px", marginBottom: 24,
    }}>
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 11, color: "#00ff87", letterSpacing: 3, fontWeight: 900 }}>
          🎯 BUILD YOUR OWN PARLAY
        </div>
        <div style={{ fontSize: 9, color: "#666", marginTop: 4 }}>
          Tap any line to add to your slip · ML · RL · TOTAL · {eligible.length} games with lines posted
        </div>
      </div>

      {eligible.map(g => {
        const ml = g.moneyline_data || {};
        const lm = g.line_movement || {};
        const aml = ml.closing_away_ml ?? ml.away_ml;
        const hml = ml.closing_home_ml ?? ml.home_ml;
        const total = lm.closing_total ?? lm.current_total;
        const matchup = `${g.away_team} @ ${g.home_team}`;
        const isAwayFav = aml != null && hml != null && aml < hml;
        const favTeam = isAwayFav ? g.away_team : g.home_team;
        const dogTeam = isAwayFav ? g.home_team : g.away_team;
        const favML = isAwayFav ? aml : hml;
        const dogML = isAwayFav ? hml : aml;
        const favRLOdds = favML != null ? favRL(favML) : null;
        const dogRLOdds = dogML != null ? dogRL(dogML) : null;
        const isPitchersDuel = (g.total_score ?? 0) >= 65;
        const isShootout = (g.total_score ?? 0) <= 35 && total != null && total >= 9;

        const Btn = ({ label, sub, odds, leg, color = "#00ff87" }) => {
          const { addLeg, isInSlip } = useBetSlip();
          const inSlip = isInSlip(leg);
          if (odds == null) {
            return (
              <button disabled style={{
                background: "#0a0a0a", border: "1px dashed #1a1a1a",
                color: "#333", padding: "8px 4px", borderRadius: 5,
                fontSize: 9, fontFamily: "monospace", cursor: "not-allowed",
                display: "flex", flexDirection: "column", gap: 2, alignItems: "center",
                minHeight: 46,
              }}>
                <div>{label}</div>
                <div style={{ fontSize: 8 }}>—</div>
              </button>
            );
          }
          return (
            <button onClick={() => addLeg({ ...leg, source: "Bet Builder" })} style={{
              background: inSlip ? color : "#0d0d0d",
              border: `1px solid ${inSlip ? color : color + "40"}`,
              color: inSlip ? "#000" : "#ddd",
              padding: "8px 4px", borderRadius: 5,
              fontSize: 10, fontFamily: "monospace", cursor: "pointer",
              display: "flex", flexDirection: "column", gap: 2, alignItems: "center",
              fontWeight: 700, transition: "all 0.15s",
            }} title={`Add ${label} to slip`}>
              <div style={{ fontSize: 9, opacity: 0.85 }}>{sub}</div>
              <div style={{ fontWeight: 900, color: inSlip ? "#000" : "#fbbf24" }}>
                {odds >= 0 ? `+${odds}` : odds}
              </div>
            </button>
          );
        };

        // Line movement: opening → current
        const openTotal = lm.opening_total;
        const totalMv = lm.total_movement;
        const awayMlMv = ml.away_ml_movement;
        const homeMlMv = ml.home_ml_movement;
        const openAML = ml.opening_away_ml;
        const openHML = ml.opening_home_ml;

        return (
          <div key={g.game_pk} style={{
            background: "#0a0a0a", border: "1px solid #1a1a1a",
            borderRadius: 8, padding: "12px", marginBottom: 10,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6, flexWrap: "wrap", gap: 6 }}>
              <div style={{ fontSize: 12, color: "#fff", fontWeight: 700 }}>{matchup}</div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                {isPitchersDuel && (
                  <span style={{ fontSize: 8, color: "#00ff87", background: "#00ff8715",
                    border: "1px solid #00ff8740", padding: "1px 5px", borderRadius: 3,
                    fontFamily: "monospace", fontWeight: 700 }}>U-LEAN</span>
                )}
                {isShootout && (
                  <span style={{ fontSize: 8, color: "#fbbf24", background: "#fbbf2415",
                    border: "1px solid #fbbf2440", padding: "1px 5px", borderRadius: 3,
                    fontFamily: "monospace", fontWeight: 700 }}>O-LEAN</span>
                )}
              </div>
            </div>

            {/* Line movement strip — sharp-money signals */}
            <LineMovementStrip
              openTotal={openTotal} curTotal={total} totalMv={totalMv}
              openAML={openAML} curAML={aml} awayMv={awayMlMv}
              openHML={openHML} curHML={hml} homeMv={homeMlMv}
              awayTeam={g.away_team_abbr || g.away_team}
              homeTeam={g.home_team_abbr || g.home_team}
            />


            {/* Markets grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
              {/* ML column */}
              <div>
                <div style={{ fontSize: 7, color: "#444", letterSpacing: 1.5, marginBottom: 4, textAlign: "center" }}>MONEYLINE</div>
                <div style={{ display: "grid", gridTemplateRows: "1fr 1fr", gap: 4 }}>
                  <Btn
                    label="Away" sub={g.away_team_abbr || "AWAY"}
                    odds={aml}
                    leg={{ matchup, play: `${g.away_team} ML`, odds: aml, type: "ML" }}
                    color="#fb7185"
                  />
                  <Btn
                    label="Home" sub={g.home_team_abbr || "HOME"}
                    odds={hml}
                    leg={{ matchup, play: `${g.home_team} ML`, odds: hml, type: "ML" }}
                    color="#fb7185"
                  />
                </div>
              </div>

              {/* RL column */}
              <div>
                <div style={{ fontSize: 7, color: "#444", letterSpacing: 1.5, marginBottom: 4, textAlign: "center" }}>RUN LINE</div>
                <div style={{ display: "grid", gridTemplateRows: "1fr 1fr", gap: 4 }}>
                  <Btn
                    label="Fav -1.5" sub={`${favTeam ? favTeam.split(" ").pop() : "FAV"} -1.5`}
                    odds={favRLOdds}
                    leg={{ matchup, play: `${favTeam} -1.5 RL`, odds: favRLOdds, type: "FAV_RL" }}
                    color="#a3e635"
                  />
                  <Btn
                    label="Dog +1.5" sub={`${dogTeam ? dogTeam.split(" ").pop() : "DOG"} +1.5`}
                    odds={dogRLOdds}
                    leg={{ matchup, play: `${dogTeam} +1.5 RL`, odds: dogRLOdds, type: "DOG_RL" }}
                    color="#a78bfa"
                  />
                </div>
              </div>

              {/* TOTAL column */}
              <div>
                <div style={{ fontSize: 7, color: "#444", letterSpacing: 1.5, marginBottom: 4, textAlign: "center" }}>TOTAL {total != null && `(${total})`}</div>
                <div style={{ display: "grid", gridTemplateRows: "1fr 1fr", gap: 4 }}>
                  <Btn
                    label="Over" sub={`O ${total ?? "—"}`}
                    odds={total != null ? -110 : null}
                    leg={{ matchup, play: `OVER ${total}`, odds: -110, type: "OVER" }}
                    color="#fbbf24"
                  />
                  <Btn
                    label="Under" sub={`U ${total ?? "—"}`}
                    odds={total != null ? -110 : null}
                    leg={{ matchup, play: `UNDER ${total}`, odds: -110, type: "UNDER" }}
                    color="#00ff87"
                  />
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Collapsible section wrapper — used to hide secondary parlay models
function CollapsibleSection({ title, subtitle, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{
      background: "#080808", border: "1px solid #1a1a1a",
      borderRadius: 8, marginBottom: 24, overflow: "hidden",
    }}>
      <button onClick={() => setOpen(o => !o)} style={{
        width: "100%", background: "transparent", border: "none",
        padding: "14px 18px", cursor: "pointer", textAlign: "left",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div>
          <div style={{ fontSize: 11, color: "#888", letterSpacing: 2.5, fontWeight: 800 }}>
            {title}
          </div>
          {subtitle && <div style={{ fontSize: 9, color: "#444", marginTop: 3 }}>{subtitle}</div>}
        </div>
        <span style={{ fontSize: 12, color: "#666", fontFamily: "monospace" }}>
          {open ? "▼ HIDE" : "▶ SHOW"}
        </span>
      </button>
      {open && (
        <div style={{ padding: "0 14px 14px", borderTop: "1px solid #1a1a1a" }}>
          <div style={{ paddingTop: 14 }}>{children}</div>
        </div>
      )}
    </div>
  );
}

function AIBoard({ aiPicks, allGames }) {
  const hasPreview = aiPicks && aiPicks.total_preview_games > 0;
  if (!hasPreview) {
    return (
      <>
        <div style={{
          background: "#fbbf2410", border: "1px solid #fbbf2430",
          borderRadius: 8, padding: "14px 18px", marginBottom: 18,
          fontSize: 11, color: "#fbbf24", textAlign: "center", lineHeight: 1.5,
        }}>
          No upcoming games on this date — switch the slate to <strong>TOMORROW</strong> above
          for the full AI board (Safe Play, Parlays, Overs/Faves, Rankings).
        </div>
        <LiveTracker games={allGames} />
      </>
    );
  }

  const {
    safe_play, top_unders = [], way_under_candidates = [], top_dogs = [],
    top_overs = [], top_faves = [], parlay = {}, power_parlay = {},
    out_the_park_parlay = {}, way_out_the_park_parlay = {},
    already_winning_parlay = {},
    nrfi_parlay = {}, f5_under_parlay = {},
    best_edge_parlay = {}, sharp_parlay = {}, formula_parlay = {},
    rankings = [], watch_list = [], skip_list = [], flagged_lines = [],
  } = aiPicks;

  return (
    <div>
      {/* THE FORMULA — flagship self-contained correlated parlay */}
      <FormulaParlayCard parlay={formula_parlay} />

      {/* HERO PICK — biggest single mispricing of the day */}
      <HeroPickCard aiPicks={aiPicks} />

      {/* Header (slimmer now that the hero card carries the weight) */}
      <div style={{
        background: "linear-gradient(135deg, #00ff8708 0%, #a78bfa08 100%)",
        border: "1px solid #1a1a1a", borderRadius: 6,
        padding: "10px 14px", marginBottom: 16,
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div style={{ fontSize: 10, color: "#666", letterSpacing: 2, fontWeight: 700 }}>
          🧠 AI INTELLIGENCE — {aiPicks.total_preview_games} UPCOMING GAMES
        </div>
      </div>

      {/* SAFE PLAY OF THE DAY — hero card */}
      {safe_play && (
        <div style={{
          background: "linear-gradient(135deg, #00ff8715, #0a0a0a)",
          border: "2px solid #00ff87", borderRadius: 10,
          padding: "18px 20px", marginBottom: 24,
          boxShadow: "0 0 28px #00ff8730",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
            <div style={{ fontSize: 11, color: "#00ff87", letterSpacing: 3, fontWeight: 900 }}>
              🔒 SAFE PLAY OF THE DAY
            </div>
            <div style={{ fontSize: 9, color: "#666", letterSpacing: 1 }}>
              {safe_play.confidence_label}
            </div>
          </div>
          <div style={{ fontSize: 18, color: "#fff", fontWeight: 900, marginTop: 4, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span>{safe_play.play}</span>
            <AddPill
              leg={{ matchup: safe_play.matchup, play: safe_play.play, odds: safe_play.odds ?? -110, type: safe_play.type || "UNDER" }}
              source="Safe Play"
              accentColor="#00ff87"
            />
          </div>
          <div style={{ fontSize: 11, color: "#a3e635", fontFamily: "monospace", marginTop: 4 }}>
            {safe_play.matchup}
            {safe_play.best_book && <span style={{ color: "#666", marginLeft: 8 }}>· best @ {safe_play.best_book}</span>}
          </div>
          <div style={{ fontSize: 10, color: "#aaa", marginTop: 10, lineHeight: 1.6 }}>
            {safe_play.safe_summary}
          </div>
          {safe_play.projected_floor && (
            <div style={{
              marginTop: 12, padding: "8px 12px",
              background: "#00ff8708", border: "1px solid #00ff8725", borderRadius: 4,
            }}>
              <div style={{ fontSize: 9, color: "#00ff87", letterSpacing: 1.5, fontWeight: 700 }}>
                FLOOR PROJECTION — game ends as low as {safe_play.projected_floor} total runs
              </div>
              {(safe_play.floor_reasoning || []).map((r, j) => (
                <div key={j} style={{ fontSize: 9, color: "#888", marginTop: 4, lineHeight: 1.4 }}>• {r}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* FLAGGED LINES — corrupted data warnings */}
      {flagged_lines.length > 0 && (
        <div style={{
          background: "#ff3b3b08", border: "1px solid #ff3b3b40",
          borderRadius: 8, padding: "12px 16px", marginBottom: 20,
        }}>
          <div style={{ fontSize: 10, color: "#ff3b3b", letterSpacing: 2, fontWeight: 900, marginBottom: 6 }}>
            ⚠ DATA QUALITY FLAGS — {flagged_lines.length} {flagged_lines.length === 1 ? "GAME" : "GAMES"}
          </div>
          {flagged_lines.map((f, i) => (
            <div key={i} style={{ fontSize: 10, color: "#aaa", marginTop: 4, fontFamily: "monospace" }}>
              <span style={{ color: "#ff3b3b" }}>•</span> {f.matchup}
              <div style={{ fontSize: 9, color: "#666", marginTop: 1, marginLeft: 10 }}>
                {f.issues.join(" · ")}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* BEST EDGE PARLAY — pure signal, highest EV legs regardless of type */}
      <BestEdgeCard parlay={best_edge_parlay} />

      {/* SHARP MONEY PARLAY — pure follow-the-line, no model overlay */}
      <SharpParlayCard parlay={sharp_parlay} />

      {/* LINE MOVEMENT BOARD — sharp-money tells from opening → current */}
      <LineMovementBoard games={allGames} />

      {/* ATS / RUN LINE — favorites -1.5 + dogs +1.5 ranked by EV */}
      <RunLinePicks topFaves={top_faves} topDogs={top_dogs} />

      {/* BUILD YOUR OWN PARLAY — game-by-game ML/RL/Total tap-to-add */}
      <BetBuilder games={allGames} />

      {/* MORE PARLAYS — collapsed by default to cut noise */}
      <CollapsibleSection title="🎟️ MORE PARLAY MODELS" subtitle="F5 · NRFI · OTP · WOTP · Value · Power · Already Winning">
        <ParlayCard parlay={f5_under_parlay} title="F5 UNDER PARLAY — NO BULLPEN RISK" accentColor="#60a5fa" icon="5️⃣" />
        <ParlayCard parlay={nrfi_parlay} title="NRFI PARLAY — STACKED 1ST INNING UNDERS" accentColor="#facc15" icon="🥚" />
        <OutTheParkCard parlay={out_the_park_parlay} />
        <WayOutTheParkCard parlay={way_out_the_park_parlay} />
        <AlreadyWinningCard parlay={already_winning_parlay} />
        <ParlayCard parlay={parlay} title="VALUE PARLAY — UNDERS + DOGS" accentColor="#fbbf24" icon="🎫" />
        <ParlayCard parlay={power_parlay} title="POWER PARLAY — OVERS + FAVES" accentColor="#fb7185" icon="🏆" />
      </CollapsibleSection>

      {/* WAY UNDER candidates */}
      {way_under_candidates.length > 0 && (
        <SectionHeader
          title="🔻🔻 WAY UNDER CANDIDATES"
          subtitle="Multiple converging signals — high probability of finishing 2+ runs UNDER"
          count={way_under_candidates.length}
        />
      )}
      {way_under_candidates.map((w, i) => (
        <div key={`way-${i}`} style={{
          background: "#0a0a0a", border: "1px solid #00ff8740",
          borderRadius: 8, padding: "14px 18px", marginBottom: 10,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <div style={{ fontSize: 13, color: "#fff", fontWeight: 700 }}>
              {w.matchup}
            </div>
            <div style={{ fontSize: 11, color: "#00ff87", fontFamily: "monospace", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
              <span>UNDER {w.closing_total ?? "TBD"}</span>
              {w.best_book && <span style={{ color: "#666", fontSize: 9 }}>@ {w.best_book}</span>}
              {w.closing_total != null && (
                <AddPill
                  leg={{ matchup: w.matchup, play: `UNDER ${w.closing_total}`, odds: w.best_price ?? -110, type: "UNDER" }}
                  source="Way Under"
                  accentColor="#00ff87"
                />
              )}
            </div>
          </div>
          <div style={{ fontSize: 9, color: "#00ff87", marginTop: 4, letterSpacing: 1 }}>
            {w.signal_count} CONVERGING SIGNALS
          </div>
          <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid #1a1a1a" }}>
            {w.converging_signals.map((s, j) => (
              <div key={j} style={{ fontSize: 10, color: "#888", fontFamily: "monospace", marginBottom: 2 }}>
                • {s}
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* TOP UNDERS */}
      <SectionHeader
        title="📉 TOP UNDER PLAYS"
        subtitle="Highest-confidence pre-flop unders by main model"
        count={top_unders.length}
      />
      {top_unders.map((u, i) => {
        const color = u.under_score >= 70 ? "#00ff87" : u.under_score >= 60 ? "#ffd700" : "#ff9500";
        return (
          <div key={`u-${i}`} style={{
            background: "#0a0a0a", border: `1px solid ${color}30`,
            borderRadius: 8, padding: "14px 18px", marginBottom: 10,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <div style={{ fontSize: 13, color: "#fff", fontWeight: 700 }}>{u.matchup}</div>
              <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                <span style={{ fontSize: 9, color: color, letterSpacing: 1.5, fontWeight: 700 }}>{u.confidence}</span>
                <span style={{ fontSize: 14, color: color, fontFamily: "monospace", fontWeight: 700 }}>
                  {Math.round(u.under_score)}
                </span>
              </div>
            </div>
            <div style={{ fontSize: 10, color: "#666", fontFamily: "monospace", marginTop: 3, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span>UNDER {u.closing_total}</span>
              {u.best_book && <span>· {u.best_price > 0 ? "+" : ""}{u.best_price} @ {u.best_book}</span>}
              <AddPill
                leg={{ matchup: u.matchup, play: `UNDER ${u.closing_total}`, odds: u.best_price ?? -110, type: "UNDER" }}
                source="Top Unders"
                accentColor={color}
              />
            </div>
            <WhyExpander reasons={u.reasons} color={color} />
          </div>
        );
      })}

      {/* TOP DOGS */}
      <SectionHeader
        title="🐕 TOP DOG UPSET PLAYS"
        subtitle="Underdogs with the strongest upset profile pre-game"
        count={top_dogs.length}
      />
      {top_dogs.map((d, i) => {
        const color = d.dog_score >= 75 ? "#a78bfa" : d.dog_score >= 65 ? "#c4b5fd" : "#9ca3af";
        return (
          <div key={`d-${i}`} style={{
            background: "#0a0a0a", border: `1px solid ${color}30`,
            borderRadius: 8, padding: "14px 18px", marginBottom: 10,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <div style={{ fontSize: 13, color: "#fff", fontWeight: 700 }}>
                {d.dog_team} <span style={{ color: "#444", fontWeight: 400, fontSize: 10 }}>ML</span>
              </div>
              <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                <span style={{ fontSize: 11, color: "#fbbf24", fontFamily: "monospace" }}>
                  {americanOdds(d.moneyline)}
                </span>
                <span style={{ fontSize: 14, color, fontFamily: "monospace", fontWeight: 700 }}>
                  {Math.round(d.dog_score)}
                </span>
              </div>
            </div>
            <div style={{ fontSize: 10, color: "#666", fontFamily: "monospace", marginTop: 3, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span>{d.matchup}</span>
              {d.best_book && <span style={{ color: "#a78bfa" }}>best @ {d.best_book}</span>}
              <AddPill
                leg={{ matchup: d.matchup, play: `${d.dog_team} ML`, odds: d.best_price ?? d.moneyline, type: "ML" }}
                source="Top Dogs"
                accentColor={color}
              />
            </div>
            <WhyExpander reasons={d.reasons} color={color} />
          </div>
        );
      })}

      {/* TOP OVERS */}
      {top_overs.length > 0 && (
        <SectionHeader
          title="📈 TOP OVER PLAYS"
          subtitle="Hot bats, weak pitching, hitter-friendly conditions"
          count={top_overs.length}
        />
      )}
      {top_overs.map((o, i) => {
        const color = o.over_score >= 70 ? "#fbbf24" : o.over_score >= 60 ? "#fde68a" : "#facc15";
        return (
          <div key={`o-${i}`} style={{
            background: "#0a0a0a", border: `1px solid ${color}30`,
            borderRadius: 8, padding: "14px 18px", marginBottom: 10,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <div style={{ fontSize: 13, color: "#fff", fontWeight: 700 }}>{o.matchup}</div>
              <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                <span style={{ fontSize: 9, color, letterSpacing: 1.5, fontWeight: 700 }}>{o.confidence}</span>
                <span style={{ fontSize: 14, color, fontFamily: "monospace", fontWeight: 700 }}>
                  {Math.round(o.over_score)}
                </span>
              </div>
            </div>
            <div style={{ fontSize: 10, color: "#666", fontFamily: "monospace", marginTop: 3, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span>OVER {o.closing_total ?? "TBD"}</span>
              {o.best_book && <span>· {o.best_price > 0 ? "+" : ""}{o.best_price} @ {o.best_book}</span>}
              {o.closing_total != null && (
                <AddPill
                  leg={{ matchup: o.matchup, play: `OVER ${o.closing_total}`, odds: o.best_price ?? -110, type: "OVER" }}
                  source="Top Overs"
                  accentColor={color}
                />
              )}
            </div>
            <WhyExpander reasons={o.reasons} color={color} />
          </div>
        );
      })}

      {/* TOP FAVES */}
      {top_faves.length > 0 && (
        <SectionHeader
          title="⭐ TOP FAVORITE PLAYS"
          subtitle="Lay the chalk when the edge is real — SP advantage, hot bats, cold opp"
          count={top_faves.length}
        />
      )}
      {top_faves.map((f, i) => {
        const color = f.fav_score >= 75 ? "#fb7185" : f.fav_score >= 65 ? "#fda4af" : "#fecdd3";
        return (
          <div key={`f-${i}`} style={{
            background: "#0a0a0a", border: `1px solid ${color}30`,
            borderRadius: 8, padding: "14px 18px", marginBottom: 10,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <div style={{ fontSize: 13, color: "#fff", fontWeight: 700 }}>
                {f.fav_team} <span style={{ color: "#666", fontWeight: 400, fontSize: 10 }}>· {f.play_suggestion}</span>
              </div>
              <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                <span style={{ fontSize: 11, color: "#fbbf24", fontFamily: "monospace" }}>
                  {americanOdds(f.moneyline)}
                </span>
                <span style={{ fontSize: 14, color, fontFamily: "monospace", fontWeight: 700 }}>
                  {Math.round(f.fav_score)}
                </span>
              </div>
            </div>
            <div style={{ fontSize: 10, color: "#666", fontFamily: "monospace", marginTop: 3, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span>{f.matchup}</span>
              <span>· {f.implied_pct}% implied</span>
              {f.best_book && <span style={{ color: "#fb7185" }}>best @ {f.best_book}</span>}
              <AddPill
                leg={{ matchup: f.matchup, play: `${f.fav_team} ML`, odds: f.best_price ?? f.moneyline, type: "ML" }}
                source="Top Faves"
                accentColor={color}
              />
            </div>
            <WhyExpander reasons={f.reasons} color={color} />
          </div>
        );
      })}

      {/* FULL BOARD RANKINGS */}
      {rankings.length > 0 && (
        <>
          <SectionHeader
            title="📊 FULL BOARD"
            subtitle="One-line read on every game with a tier rating"
            count={rankings.length}
          />
          <div style={{ background: "#0a0a0a", border: "1px solid #1a1a1a", borderRadius: 8, padding: "8px 4px" }}>
            {rankings.map((r, i) => (
              <div key={`rank-${i}`} style={{
                padding: "8px 12px",
                borderBottom: i < rankings.length - 1 ? "1px solid #141414" : "none",
                display: "flex", gap: 10, alignItems: "center",
              }}>
                <TierChip tier={r.tier} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 11, color: "#ddd", fontWeight: 600 }}>
                    {r.matchup}
                  </div>
                  <div style={{ fontSize: 9, color: "#666", marginTop: 2, fontFamily: "monospace" }}>
                    <span style={{ color: r.tier === "skip" ? "#555" : "#fbbf24" }}>{r.play}</span>
                    <span style={{ marginLeft: 8 }}>· {r.edge_note}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* WATCH LIST */}
      {watch_list.length > 0 && (
        <>
          <SectionHeader
            title="👁 WATCH LIST"
            subtitle="Value spots where the line/data needs to firm up — re-check closer to first pitch"
            count={watch_list.length}
          />
          {watch_list.map((w, i) => (
            <div key={`watch-${i}`} style={{
              background: "#0a0a0a", border: "1px solid #fbbf2430",
              borderRadius: 8, padding: "12px 16px", marginBottom: 8,
            }}>
              <div style={{ fontSize: 12, color: "#fff", fontWeight: 700 }}>
                {w.matchup}
              </div>
              <div style={{ fontSize: 10, color: "#fbbf24", fontFamily: "monospace", marginTop: 4 }}>
                Watch for: {w.watch_for}
              </div>
              <div style={{ fontSize: 9, color: "#666", marginTop: 4, lineHeight: 1.5 }}>
                {w.reason}
              </div>
            </div>
          ))}
        </>
      )}

      {/* SKIP LIST */}
      {skip_list.length > 0 && (
        <>
          <SectionHeader
            title="✗ SKIP LIST"
            subtitle="Avoid these — variance too high or no model edge"
            count={skip_list.length}
          />
          {skip_list.map((s, i) => (
            <div key={`skip-${i}`} style={{
              background: "#0a0a0a", border: "1px solid #ff3b3b25",
              borderRadius: 8, padding: "10px 14px", marginBottom: 6,
            }}>
              <div style={{ fontSize: 11, color: "#aaa", fontWeight: 600 }}>
                {s.matchup}
              </div>
              {s.reasons.map((r, j) => (
                <div key={j} style={{ fontSize: 9, color: "#666", marginTop: 3, fontFamily: "monospace" }}>
                  • {r}
                </div>
              ))}
            </div>
          ))}
        </>
      )}

      {/* Live tracker always shown below pre-game picks */}
      <LiveTracker games={allGames} />
    </div>
  );
}

// ─── MAIN APP ────────────────────────────────────────────────────────────────

// ── Floating Bet Slip drawer ─────────────────────────────────────────────────
function BetSlipFAB() {
  const { slip, drawerOpen, setDrawerOpen } = useBetSlip();
  if (drawerOpen) return null;
  const count = slip.length;
  return (
    <button onClick={() => setDrawerOpen(true)} style={{
      position: "fixed", bottom: 18, right: 18, zIndex: 100,
      background: count > 0 ? "linear-gradient(135deg, #00ff87, #34d399)" : "#1a1a1a",
      color: count > 0 ? "#000" : "#666",
      border: count > 0 ? "2px solid #00ff87" : "2px solid #2a2a2a",
      borderRadius: 30, padding: "14px 20px",
      fontSize: 12, fontFamily: "monospace", fontWeight: 900,
      letterSpacing: 1.5, cursor: "pointer",
      boxShadow: count > 0 ? "0 6px 24px #00ff8745" : "0 4px 12px #00000060",
      display: "flex", alignItems: "center", gap: 8,
      transition: "all 0.2s",
    }}>
      🎟️ BET SLIP
      <span style={{
        background: count > 0 ? "#000" : "#2a2a2a",
        color: count > 0 ? "#00ff87" : "#444",
        borderRadius: "50%", width: 22, height: 22,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        fontSize: 11, fontWeight: 900,
      }}>{count}</span>
    </button>
  );
}

function BetSlipDrawer() {
  const { slip, wager, setWager, drawerOpen, setDrawerOpen, removeLeg, clearSlip } = useBetSlip();
  const { placed, placeBet, updateStatus, removePlaced, clearAllPlaced } = usePlaced();
  const [tab, setTab] = useState("potential");  // "potential" | "placed"

  // Math
  const oddsToDecimal = (am) => am >= 0 ? 1 + am / 100 : 1 + 100 / Math.abs(am);
  const oddsToProb = (am) => am >= 0 ? 100 / (am + 100) : Math.abs(am) / (Math.abs(am) + 100);
  const formatAmerican = (dec) => {
    if (dec <= 1) return "—";
    const a = dec >= 2 ? Math.round((dec - 1) * 100) : Math.round(-100 / (dec - 1));
    return a >= 0 ? `+${a}` : `${a}`;
  };

  const wagerAmt = parseFloat(wager) || 0;
  const validLegs = slip.filter(l => typeof l.odds === "number" && !isNaN(l.odds));
  const combinedDecimal = validLegs.reduce((acc, l) => acc * oddsToDecimal(l.odds), 1);
  const combinedProb = validLegs.reduce((acc, l) => acc * oddsToProb(l.odds), 1);
  const payout = wagerAmt * combinedDecimal;
  const profit = payout - wagerAmt;

  const isParlay = validLegs.length >= 2;
  const isSingle = validLegs.length === 1;

  const handlePlaceBet = () => {
    if (!validLegs.length || wagerAmt <= 0) return;
    placeBet(validLegs, wager);
    clearSlip();
    setTab("placed");
  };

  if (!drawerOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div onClick={() => setDrawerOpen(false)} style={{
        position: "fixed", inset: 0, background: "#000000aa", zIndex: 200,
        backdropFilter: "blur(2px)",
      }} />

      {/* Drawer */}
      <div style={{
        position: "fixed", top: 0, right: 0, bottom: 0,
        width: "min(420px, 100vw)", zIndex: 201,
        background: "linear-gradient(180deg, #050505 0%, #0a0a0a 100%)",
        borderLeft: "1px solid #1a1a1a", boxShadow: "-12px 0 40px #000",
        display: "flex", flexDirection: "column",
        fontFamily: "monospace",
      }}>
        {/* Header */}
        <div style={{
          padding: "16px 18px",
          borderBottom: "1px solid #1a1a1a",
          display: "flex", justifyContent: "space-between", alignItems: "center",
          background: "linear-gradient(135deg, #00ff8708, transparent)",
        }}>
          <div>
            <div style={{ fontSize: 14, color: "#00ff87", fontWeight: 900, letterSpacing: 2 }}>
              🎟️ BET SLIP
            </div>
            <div style={{ fontSize: 9, color: "#444", marginTop: 2 }}>
              {validLegs.length} {validLegs.length === 1 ? "leg" : "legs"} · click any pick to add
            </div>
          </div>
          <button onClick={() => setDrawerOpen(false)} style={{
            background: "transparent", border: "1px solid #2a2a2a",
            color: "#666", fontSize: 14, cursor: "pointer",
            padding: "4px 12px", borderRadius: 4,
          }}>✕</button>
        </div>

        {/* Tab switch */}
        <div style={{ display: "flex", borderBottom: "1px solid #1a1a1a" }}>
          {[
            { key: "potential", label: `POTENTIAL · ${validLegs.length}` },
            { key: "placed",    label: `PLACED · ${placed.length}` },
          ].map(({ key, label }) => (
            <button key={key} onClick={() => setTab(key)} style={{
              flex: 1, background: "transparent", border: "none",
              borderBottom: tab === key ? "2px solid #00ff87" : "2px solid transparent",
              color: tab === key ? "#fff" : "#444",
              padding: "10px", fontSize: 10, fontFamily: "monospace",
              letterSpacing: 1.5, fontWeight: 700, cursor: "pointer",
            }}>{label}</button>
          ))}
        </div>

        {/* PLACED tab content */}
        {tab === "placed" && (
          <div style={{ flex: 1, overflowY: "auto", padding: "10px 14px" }}>
            {placed.length === 0 ? (
              <div style={{ textAlign: "center", color: "#333", padding: "40px 20px" }}>
                <div style={{ fontSize: 32, marginBottom: 10, opacity: 0.4 }}>📋</div>
                <div style={{ fontSize: 10, color: "#555", lineHeight: 1.5 }}>
                  No placed bets yet.<br/>Build a slip in <strong>POTENTIAL</strong> and tap <strong style={{ color: "#00ff87" }}>PLACE BET</strong>.
                </div>
              </div>
            ) : (
              <>
                {placed.map(b => {
                  const dec = parlayOdds(b.legs);
                  const pay = b.wager * dec;
                  const statusColor = b.status === "WON" ? "#00ff87" : b.status === "LOST" ? "#ff3b3b" : b.status === "PUSH" ? "#888" : "#fbbf24";
                  const placedDate = new Date(b.placedAt).toLocaleDateString("en-CA", { timeZone: "America/Los_Angeles" });
                  const placedTime = new Date(b.placedAt).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/Los_Angeles" });
                  return (
                    <div key={b.id} style={{
                      background: "#0a0a0a", border: `1px solid ${statusColor}40`,
                      borderRadius: 8, padding: "10px 12px", marginBottom: 8,
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                        <div style={{ fontSize: 8, color: "#444", letterSpacing: 1.5 }}>
                          {placedDate} {placedTime} PT · {b.legs.length}-LEG
                        </div>
                        <span style={{
                          fontSize: 9, fontWeight: 900, letterSpacing: 1.5,
                          color: statusColor, background: statusColor + "18",
                          border: `1px solid ${statusColor}50`,
                          padding: "1px 6px", borderRadius: 3,
                        }}>{b.status}</span>
                      </div>
                      {b.legs.map((leg, i) => (
                        <div key={i} style={{ fontSize: 10, color: "#bbb", marginBottom: 2 }}>
                          <span style={{ color: "#666" }}>#{i+1} </span>
                          {leg.play}
                          <span style={{ color: "#fbbf24", marginLeft: 6, fontFamily: "monospace" }}>
                            {leg.odds >= 0 ? `+${leg.odds}` : leg.odds}
                          </span>
                          <div style={{ fontSize: 8, color: "#444", marginLeft: 16 }}>{leg.matchup}</div>
                        </div>
                      ))}
                      <div style={{
                        marginTop: 6, paddingTop: 6, borderTop: "1px solid #1a1a1a",
                        display: "flex", justifyContent: "space-between", alignItems: "center",
                      }}>
                        <div style={{ fontSize: 9, color: "#888", fontFamily: "monospace" }}>
                          ${b.wager} → <span style={{ color: "#00ff87" }}>${pay.toFixed(2)}</span>
                        </div>
                        {b.status === "PENDING" ? (
                          <div style={{ display: "flex", gap: 4 }}>
                            <button onClick={() => updateStatus(b.id, "WON")} style={{
                              background: "#00ff8718", color: "#00ff87",
                              border: "1px solid #00ff8750", borderRadius: 4,
                              fontSize: 9, fontWeight: 800, padding: "3px 10px",
                              cursor: "pointer", fontFamily: "monospace", letterSpacing: 1,
                            }}>✓ W</button>
                            <button onClick={() => updateStatus(b.id, "LOST")} style={{
                              background: "#ff3b3b18", color: "#ff3b3b",
                              border: "1px solid #ff3b3b50", borderRadius: 4,
                              fontSize: 9, fontWeight: 800, padding: "3px 10px",
                              cursor: "pointer", fontFamily: "monospace", letterSpacing: 1,
                            }}>✕ L</button>
                            <button onClick={() => updateStatus(b.id, "PUSH")} style={{
                              background: "#88888818", color: "#888",
                              border: "1px solid #88888850", borderRadius: 4,
                              fontSize: 9, fontWeight: 800, padding: "3px 10px",
                              cursor: "pointer", fontFamily: "monospace", letterSpacing: 1,
                            }}>= P</button>
                          </div>
                        ) : (
                          <button onClick={() => updateStatus(b.id, "PENDING")} style={{
                            background: "transparent", color: "#444",
                            border: "1px solid #1a1a1a", borderRadius: 4,
                            fontSize: 8, padding: "2px 8px", cursor: "pointer",
                            fontFamily: "monospace", letterSpacing: 1,
                          }}>UNDO</button>
                        )}
                        <button onClick={() => removePlaced(b.id)} style={{
                          background: "transparent", border: "none",
                          color: "#333", fontSize: 14, cursor: "pointer", padding: "0 2px",
                        }}>×</button>
                      </div>
                    </div>
                  );
                })}
                {placed.length > 0 && (
                  <button onClick={() => { if (confirm("Clear all placed bets and reset track record?")) clearAllPlaced(); }} style={{
                    width: "100%", marginTop: 8, background: "transparent",
                    border: "1px solid #1a1a1a", color: "#444",
                    fontSize: 9, fontFamily: "monospace", letterSpacing: 1.5,
                    padding: "8px", borderRadius: 6, cursor: "pointer",
                  }}>RESET TRACK RECORD</button>
                )}
              </>
            )}
          </div>
        )}

        {/* POTENTIAL tab content — empty state */}
        {tab === "potential" && validLegs.length === 0 && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", color: "#333",
            padding: "40px 20px", textAlign: "center" }}>
            <div style={{ fontSize: 36, marginBottom: 12, opacity: 0.4 }}>🎟️</div>
            <div style={{ fontSize: 12, color: "#666", letterSpacing: 1.5, fontWeight: 700, marginBottom: 6 }}>
              SLIP IS EMPTY
            </div>
            <div style={{ fontSize: 10, color: "#444", lineHeight: 1.5, maxWidth: 240 }}>
              Tap <span style={{ color: "#00ff87" }}>+ ADD</span> on any pick to start building.
              Then tap <strong style={{ color: "#fff" }}>PLACE BET</strong> to lock it in for tracking.
            </div>
          </div>
        )}

        {/* POTENTIAL tab content — legs list */}
        {tab === "potential" && validLegs.length > 0 && (
          <div style={{ flex: 1, overflowY: "auto", padding: "10px 14px" }}>
            {validLegs.map((leg, i) => {
              const prob = oddsToProb(leg.odds) * 100;
              return (
                <div key={leg.id} style={{
                  background: "#0a0a0a", border: "1px solid #1a1a1a",
                  borderRadius: 8, padding: "10px 12px", marginBottom: 8,
                  display: "flex", flexDirection: "column", gap: 4,
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{
                      width: 18, height: 18, borderRadius: "50%",
                      background: "#00ff8720", color: "#00ff87",
                      fontSize: 9, fontWeight: 900,
                      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                    }}>{i + 1}</span>
                    <span style={{ fontSize: 12, color: "#fff", fontWeight: 700, flex: 1, minWidth: 0 }}>
                      {leg.play}
                    </span>
                    <span style={{ fontSize: 12, color: "#fbbf24", fontFamily: "monospace", fontWeight: 700 }}>
                      {leg.odds >= 0 ? `+${leg.odds}` : leg.odds}
                    </span>
                    <button onClick={() => removeLeg(leg.id)} style={{
                      background: "transparent", border: "none",
                      color: "#444", fontSize: 16, cursor: "pointer",
                      padding: "0 4px", lineHeight: 1,
                    }}>×</button>
                  </div>
                  <div style={{ fontSize: 9, color: "#555", paddingLeft: 26,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {leg.matchup}
                  </div>
                  <div style={{ display: "flex", gap: 10, paddingLeft: 26 }}>
                    <span style={{ fontSize: 8, color: "#444" }}>{prob.toFixed(1)}% implied</span>
                    {leg.source && <span style={{ fontSize: 8, color: "#444" }}>· from {leg.source}</span>}
                    {leg.edge && leg.edge.tier && leg.edge.tier !== "UNPRICED" && (
                      <span style={{ fontSize: 8, color: leg.edge.color || "#666", fontWeight: 700 }}>
                        {leg.edge.icon} {leg.edge.tier}
                        {leg.edge.edge_pct != null ? ` ${leg.edge.edge_pct > 0 ? '+' : ''}${leg.edge.edge_pct}%` : ""}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
            <button onClick={clearSlip} style={{
              width: "100%", marginTop: 6, background: "transparent",
              border: "1px solid #1a1a1a", color: "#444",
              fontSize: 9, fontFamily: "monospace", letterSpacing: 1.5,
              padding: "8px", borderRadius: 6, cursor: "pointer",
            }}>CLEAR ALL LEGS</button>
          </div>
        )}

        {/* Wager + Payout (only on POTENTIAL tab) */}
        {tab === "potential" && validLegs.length > 0 && (
          <div style={{ borderTop: "2px solid #1a1a1a", padding: "16px 18px",
            background: "linear-gradient(180deg, transparent, #00ff8708)" }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10 }}>
              <span style={{ fontSize: 9, color: "#666", letterSpacing: 2, minWidth: 50 }}>WAGER $</span>
              <input
                type="number" min="1" value={wager}
                onChange={e => setWager(e.target.value)}
                style={{
                  flex: 1, background: "#111", border: "1px solid #2a2a2a",
                  color: "#fbbf24", fontSize: 16, fontWeight: 900,
                  fontFamily: "monospace", padding: "7px 10px", borderRadius: 5,
                  outline: "none", maxWidth: 110,
                }}
              />
              <div style={{ display: "flex", gap: 4 }}>
                {[25, 50, 100, 500].map(v => (
                  <button key={v} onClick={() => setWager(String(v))} style={{
                    background: wager == v ? "#1a1a1a" : "transparent",
                    border: `1px solid ${wager == v ? "#2a2a2a" : "#111"}`,
                    color: wager == v ? "#fff" : "#444",
                    fontSize: 9, fontFamily: "monospace",
                    padding: "3px 8px", borderRadius: 3, cursor: "pointer",
                  }}>${v}</button>
                ))}
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div style={{ background: "#0a0a0a", border: "1px solid #1a1a1a",
                borderRadius: 6, padding: "10px 12px", textAlign: "center" }}>
                <div style={{ fontSize: 8, color: "#444", letterSpacing: 1.5, marginBottom: 4 }}>
                  {isParlay ? "PARLAY ODDS" : "ODDS"}
                </div>
                <div style={{ fontSize: 18, color: isParlay ? "#a78bfa" : "#fbbf24",
                  fontWeight: 900, fontFamily: "monospace", lineHeight: 1 }}>
                  {formatAmerican(combinedDecimal)}
                </div>
                <div style={{ fontSize: 8, color: "#333", marginTop: 3 }}>
                  {(combinedProb * 100).toFixed(2)}%
                </div>
              </div>
              <div style={{ background: "#0a0a0a", border: "1px solid #00ff8730",
                borderRadius: 6, padding: "10px 12px", textAlign: "center",
                boxShadow: "0 0 12px #00ff8715" }}>
                <div style={{ fontSize: 8, color: "#444", letterSpacing: 1.5, marginBottom: 4 }}>
                  PAYOUT
                </div>
                <div style={{ fontSize: 18, color: "#00ff87", fontWeight: 900,
                  fontFamily: "monospace", lineHeight: 1 }}>
                  ${payout.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <div style={{ fontSize: 8, color: "#00ff8770", marginTop: 3 }}>
                  +${profit.toLocaleString(undefined, { maximumFractionDigits: 2 })} profit
                </div>
              </div>
            </div>

            {/* PLACE BET — locks the slip into the tracking log */}
            <button onClick={handlePlaceBet} disabled={wagerAmt <= 0} style={{
              width: "100%", marginTop: 12,
              background: wagerAmt > 0 ? "linear-gradient(135deg, #00ff87, #34d399)" : "#1a1a1a",
              color: wagerAmt > 0 ? "#000" : "#444",
              border: "none", borderRadius: 8,
              padding: "14px", fontSize: 12, fontWeight: 900,
              fontFamily: "monospace", letterSpacing: 2,
              cursor: wagerAmt > 0 ? "pointer" : "not-allowed",
              boxShadow: wagerAmt > 0 ? "0 4px 16px #00ff8740" : "none",
            }}>
              {wagerAmt > 0 ? `📥 PLACE BET — $${wagerAmt} TO WIN $${profit.toFixed(2)}` : "ENTER WAGER TO PLACE"}
            </button>
            <div style={{ fontSize: 8, color: "#333", textAlign: "center", marginTop: 6, lineHeight: 1.4 }}>
              "Placing" saves locally to your track record · mark W/L manually as games settle
            </div>
          </div>
        )}
      </div>
    </>
  );
}

export default function DiamondCodeApp() {
  return (
    <BetSlipProvider>
      <DiamondCode />
      <BetSlipFAB />
      <BetSlipDrawer />
    </BetSlipProvider>
  );
}

function DiamondCode() {
  const [slate, setSlate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [filter, setFilter] = useState("all");
  const [view, setView] = useState("ai");
  const [dateOffset, setDateOffset] = useState(0); // 0 = today, 1 = tomorrow

  const [aiPicks, setAiPicks] = useState(null);

  // All "today" / "tomorrow" rolls based on Pacific Time — MLB schedule's home zone
  const pacificDateString = (offsetDays = 0) => {
    const ms = Date.now() + offsetDays * 86400000;
    return new Date(ms).toLocaleDateString("en-CA", { timeZone: "America/Los_Angeles" });
  };

  const targetDate = pacificDateString(dateOffset);

  const fetchSlate = async () => {
    setLoading(true);
    setError(null);
    try {
      const apiBase = import.meta.env.VITE_API_URL || "";
      const res = await fetch(`${apiBase}/api/v1/games/ai-picks?game_date=${targetDate}`);
      if (!res.ok) throw new Error(`API ${res.status}`);
      const data = await res.json();
      setSlate({ games: data.games, total_games: data.games?.length ?? 0, date: targetDate, scored_games: data.games?.length ?? 0 });
      setAiPicks(data.ai_picks);
      setLastRefresh(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchSlate(); }, [dateOffset]);

  const allGames = slate?.games ?? [];

  // Auto-switch to tomorrow when all today's games are done and no preview games remain
  useEffect(() => {
    if (dateOffset !== 0 || !slate || loading) return;
    const hasPreviewOrLive = allGames.some(g => g.abstract_state === "Preview" || g.abstract_state === "Live");
    const hasGames = allGames.length > 0;
    if (hasGames && !hasPreviewOrLive) {
      setDateOffset(1);
    }
  }, [allGames, slate, loading]);

  // Auto-refresh every 30s when games are live (in-progress)
  useEffect(() => {
    const hasLive = allGames.some(g => g.abstract_state === "Live");
    if (!hasLive) return;
    const id = setInterval(() => { fetchSlate(); }, 30000);
    return () => clearInterval(id);
  }, [allGames]);

  // New-day detection: refetch when tab regains focus or once a minute if Pacific date has rolled over
  useEffect(() => {
    let lastDate = pacificDateString(0);
    const checkNewDay = () => {
      const today = pacificDateString(0);
      if (today !== lastDate) { lastDate = today; setDateOffset(0); }
    };
    const onVisibility = () => { if (document.visibilityState === "visible") checkNewDay(); };
    document.addEventListener("visibilitychange", onVisibility);
    const id = setInterval(checkNewDay, 60000);
    return () => { document.removeEventListener("visibilitychange", onVisibility); clearInterval(id); };
  }, []);
  const locks = allGames.filter(g => g.total_score >= 80);
  const strong = allGames.filter(g => g.total_score >= 65 && g.total_score < 80);
  const doubleLocks = allGames.filter(g => g.correlation?.is_double_lock);

  const displayed = filter === "locks" ? allGames.filter(g => g.total_score >= 65)
    : filter === "dogs" ? allGames.filter(g => (g.dog_score?.home_dog_score ?? 0) >= 65 || (g.dog_score?.away_dog_score ?? 0) >= 65)
    : filter === "double" ? doubleLocks
    : allGames;

  return (
    <div style={{ minHeight: "100vh", background: "#050505", color: "#e0e0e0", fontFamily: "monospace", padding: "24px 16px 100px", maxWidth: 860, margin: "0 auto" }}>

      {/* Header */}
      <div style={{ marginBottom: 24, borderBottom: "1px solid #1a1a1a", paddingBottom: 18 }}>
        <div style={{ fontSize: 9, color: "#444", letterSpacing: 4, textTransform: "uppercase", marginBottom: 5 }}>MLB UNDER + DOG SCANNER</div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <div style={{ fontSize: 26, fontWeight: 900, color: "#fff", letterSpacing: -1 }}>
              DIAMOND<span style={{ color: "#00ff87" }}>CODE</span>
            </div>
            <div style={{ fontSize: 10, color: "#333", marginTop: 3 }}>
              Park · Pitcher · Weather · Umpire · Fatigue · Lines · Bullpen · Dog
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <button onClick={fetchSlate} disabled={loading} style={{
              background: "transparent", border: "1px solid #2a2a2a",
              color: loading ? "#333" : "#00ff87", padding: "8px 14px",
              borderRadius: 4, fontSize: 9, fontFamily: "monospace",
              letterSpacing: 2, cursor: "pointer",
            }}>
              {loading ? "LOADING..." : "↻ REFRESH"}
            </button>
            {lastRefresh && <div style={{ fontSize: 8, color: "#2a2a2a", marginTop: 3 }}>{lastRefresh.toLocaleTimeString()}</div>}
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{ background: "#ff3b3b12", border: "1px solid #ff3b3b25", borderRadius: 6, padding: "12px 16px", marginBottom: 18 }}>
          <div style={{ color: "#ff3b3b", fontSize: 10 }}>⚠ Could not reach the DiamondCode server — retrying automatically</div>
          <div style={{ color: "#333", fontSize: 9, marginTop: 3 }}>{error}</div>
        </div>
      )}

      {/* Date toggle — Today / Tomorrow */}
      {slate && !loading && (
        <div style={{ display: "flex", gap: 6, marginBottom: 12, alignItems: "center", justifyContent: "flex-end" }}>
          <span style={{ fontSize: 9, color: "#444", letterSpacing: 2, marginRight: 8 }}>SLATE:</span>
          {[
            { offset: 0, label: "TODAY" },
            { offset: 1, label: "TOMORROW" },
          ].map(({ offset, label }) => (
            <button key={offset} onClick={() => setDateOffset(offset)} style={{
              background: dateOffset === offset ? "#1a1a1a" : "transparent",
              border: `1px solid ${dateOffset === offset ? "#00ff8740" : "#1a1a1a"}`,
              color: dateOffset === offset ? "#00ff87" : "#555",
              padding: "5px 12px", borderRadius: 4, fontSize: 9,
              fontFamily: "monospace", letterSpacing: 1.5, cursor: "pointer", fontWeight: 700,
            }}>{label}</button>
          ))}
          <span style={{ fontSize: 9, color: "#333", marginLeft: 8, fontFamily: "monospace" }}>{targetDate}</span>
        </div>
      )}

      {/* View switch — AI · SLATE · EDGE */}
      {slate && !loading && (
        <div style={{ display: "flex", gap: 0, marginBottom: 18, borderBottom: "1px solid #1a1a1a" }}>
          {[
            { key: "ai",    label: "🧠 AI PICKS", desc: "Recs + parlay of the day" },
            { key: "slate", label: "📋 SLATE",    desc: "Full under + dog model" },
            { key: "edge",  label: "⚡ EDGE",     desc: "NRFI · F5 · Pen · TT" },
            { key: "track", label: "📒 TRACK",    desc: "Record · CLV · results" },
          ].map(({ key, label, desc }) => (
            <button key={key} onClick={() => setView(key)} style={{
              flex: 1, background: "transparent",
              border: "none",
              borderBottom: view === key ? "2px solid #00ff87" : "2px solid transparent",
              color: view === key ? "#fff" : "#444",
              padding: "12px 16px", fontSize: 11, fontFamily: "monospace",
              letterSpacing: 2, cursor: "pointer", fontWeight: 700,
            }}>
              <div>{label}</div>
              <div style={{ fontSize: 8, color: view === key ? "#666" : "#2a2a2a", marginTop: 2, letterSpacing: 1, fontWeight: 400 }}>{desc}</div>
            </button>
          ))}
        </div>
      )}

      {/* Stats */}
      {slate && !loading && view === "slate" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 20 }}>
          {[
            { label: "GAMES", value: slate.total_games },
            { label: "LOCKS", value: locks.length, color: "#00ff87" },
            { label: "STRONG", value: strong.length, color: "#ffd700" },
            { label: "DBL LOCK", value: doubleLocks.length, color: "#a78bfa" },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: "#0a0a0a", border: "1px solid #1a1a1a", borderRadius: 6, padding: "10px 12px", textAlign: "center" }}>
              <div style={{ fontSize: 20, fontWeight: 900, color: color || "#fff" }}>{value}</div>
              <div style={{ fontSize: 8, color: "#444", letterSpacing: 2, marginTop: 1 }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* EDGE stats bar */}
      {slate && !loading && view === "edge" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 20 }}>
          {[
            { label: "NRFI 60+", value: allGames.filter(g => (g.nrfi?.nrfi_probability ?? 0) >= 60).length, color: "#00ff87" },
            { label: "F5 65+",   value: allGames.filter(g => (g.f5?.f5_score ?? 0) >= 65).length, color: "#ffd700" },
            { label: "PEN 64+",  value: allGames.filter(g => (g.late_innings?.late_score ?? 0) >= 64).length, color: "#60a5fa" },
            { label: "TT 65+",   value: allGames.filter(g => (g.team_totals?.best_score ?? 0) >= 65).length, color: "#a78bfa" },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: "#0a0a0a", border: "1px solid #1a1a1a", borderRadius: 6, padding: "10px 12px", textAlign: "center" }}>
              <div style={{ fontSize: 20, fontWeight: 900, color }}>{value}</div>
              <div style={{ fontSize: 8, color: "#444", letterSpacing: 2, marginTop: 1 }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filter tabs — only on SLATE view */}
      {slate && !loading && view === "slate" && (
        <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
          {[
            { key: "all", label: "ALL GAMES" },
            { key: "locks", label: "LOCKS 65+" },
            { key: "dogs", label: "DOG PLAYS" },
            { key: "double", label: "🔥 DBL LOCK" },
          ].map(({ key, label }) => (
            <button key={key} onClick={() => setFilter(key)} style={{
              background: filter === key ? "#1a1a1a" : "transparent",
              border: `1px solid ${filter === key ? "#2a2a2a" : "#1a1a1a"}`,
              color: filter === key ? "#fff" : "#444",
              padding: "6px 12px", borderRadius: 4, fontSize: 9,
              fontFamily: "monospace", letterSpacing: 1, cursor: "pointer",
            }}>{label}</button>
          ))}
        </div>
      )}

      {loading && <div style={{ textAlign: "center", padding: "60px 0", color: "#333", fontSize: 10, letterSpacing: 3 }}>PULLING TODAY'S SLATE...</div>}

      {!loading && view === "slate" && displayed.map((game, i) => <GameCard key={game.game_pk ?? i} game={game} />)}

      {!loading && view === "edge" && <EdgeBoard games={allGames} />}

      {!loading && view === "ai" && <AIBoard aiPicks={aiPicks} allGames={allGames} />}

      {view === "track" && <TrackBoard games={allGames} />}

      {!loading && view === "slate" && displayed.length === 0 && !error && (
        <div style={{ textAlign: "center", padding: "40px 0", color: "#2a2a2a", fontSize: 11 }}>No games match this filter.</div>
      )}

      <Legend />
      <div style={{ textAlign: "center", marginTop: 18, fontSize: 8, color: "#1a1a1a", letterSpacing: 2 }}>
        DIAMONDCODE v3.0 · INFORMATIONAL USE ONLY · GAMBLE RESPONSIBLY
      </div>
    </div>
  );
}
