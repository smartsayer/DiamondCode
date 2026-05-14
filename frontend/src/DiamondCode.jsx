import { useState, useEffect } from "react";

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

function ParlayCard({ parlay, title, accentColor, icon }) {
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
    nrfi_parlay = {}, f5_under_parlay = {}, team_total_parlay = {},
    best_edge_parlay = {},
    rankings = [], watch_list = [], skip_list = [], flagged_lines = [],
  } = aiPicks;

  return (
    <div>
      {/* Header */}
      <div style={{
        background: "linear-gradient(135deg, #00ff8710 0%, #a78bfa10 100%)",
        border: "1px solid #00ff8730", borderRadius: 8,
        padding: "16px 20px", marginBottom: 20,
      }}>
        <div style={{ fontSize: 11, color: "#00ff87", letterSpacing: 3, fontWeight: 900 }}>
          🧠 AI INTELLIGENCE
        </div>
        <div style={{ fontSize: 10, color: "#666", marginTop: 6, lineHeight: 1.5 }}>
          Synthesized from {aiPicks.total_preview_games} upcoming games. Safe play, structured parlay,
          full-board ranking, value-watch list, and lines flagged as bad data.
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
          <div style={{ fontSize: 18, color: "#fff", fontWeight: 900, marginTop: 4 }}>
            {safe_play.play}
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

      {/* VALUE PARLAY (unders + dogs) */}
      {/* BEST EDGE PARLAY — pure signal, highest EV legs regardless of type */}
      <BestEdgeCard parlay={best_edge_parlay} />

      <ParlayCard parlay={parlay} title="VALUE PARLAY — UNDERS + DOGS" accentColor="#fbbf24" icon="🎫" />

      {/* POWER PARLAY (overs + faves) */}
      <ParlayCard parlay={power_parlay} title="BEST PARLAY OF THE DAY" accentColor="#fb7185" icon="🏆" />

      {/* NRFI PARLAY (No Run First Inning) */}
      {/* ALREADY WINNING PARLAY */}
      <AlreadyWinningCard parlay={already_winning_parlay} />

      <ParlayCard parlay={nrfi_parlay} title="NRFI PARLAY — STACKED 1ST INNING UNDERS" accentColor="#facc15" icon="🥚" />

      {/* F5 UNDER PARLAY (First 5 innings) */}
      <ParlayCard parlay={f5_under_parlay} title="F5 UNDER PARLAY — NO BULLPEN RISK" accentColor="#60a5fa" icon="5️⃣" />

      {/* TEAM TOTAL PARLAY */}
      <ParlayCard parlay={team_total_parlay} title="TEAM TOTAL PARLAY — INDIVIDUAL CAPS" accentColor="#34d399" icon="🎯" />

      {/* OUT THE PARK PARLAY (extreme reverse tease — 1.5 runs against you) */}
      <OutTheParkCard parlay={out_the_park_parlay} />

      {/* WAY OUT THE PARK (faves -2.5, dogs -1.5, unders -2 — wildest swing) */}
      <WayOutTheParkCard parlay={way_out_the_park_parlay} />

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
            <div style={{ fontSize: 11, color: "#00ff87", fontFamily: "monospace", fontWeight: 700 }}>
              UNDER {w.closing_total ?? "TBD"}
              {w.best_book && <span style={{ color: "#666", marginLeft: 6, fontSize: 9 }}>@ {w.best_book}</span>}
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
            <div style={{ fontSize: 10, color: "#666", fontFamily: "monospace", marginTop: 3 }}>
              UNDER {u.closing_total}
              {u.best_book && <span style={{ marginLeft: 8 }}>· {u.best_price > 0 ? "+" : ""}{u.best_price} @ {u.best_book}</span>}
            </div>
            <div style={{ marginTop: 6 }}>
              {u.reasons.map((r, j) => (
                <div key={j} style={{ fontSize: 9, color: "#666", marginBottom: 2 }}>• {r}</div>
              ))}
            </div>
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
            <div style={{ fontSize: 10, color: "#666", fontFamily: "monospace", marginTop: 3 }}>
              {d.matchup}
              {d.best_book && <span style={{ color: "#a78bfa", marginLeft: 8 }}>best @ {d.best_book}</span>}
            </div>
            <div style={{ marginTop: 6 }}>
              {d.reasons.map((r, j) => (
                <div key={j} style={{ fontSize: 9, color: "#666", marginBottom: 2 }}>• {r}</div>
              ))}
            </div>
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
            <div style={{ fontSize: 10, color: "#666", fontFamily: "monospace", marginTop: 3 }}>
              OVER {o.closing_total ?? "TBD"}
              {o.best_book && <span style={{ marginLeft: 8 }}>· {o.best_price > 0 ? "+" : ""}{o.best_price} @ {o.best_book}</span>}
            </div>
            <div style={{ marginTop: 6 }}>
              {o.reasons.map((r, j) => (
                <div key={j} style={{ fontSize: 9, color: "#666", marginBottom: 2 }}>• {r}</div>
              ))}
            </div>
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
            <div style={{ fontSize: 10, color: "#666", fontFamily: "monospace", marginTop: 3 }}>
              {f.matchup}
              <span style={{ marginLeft: 8 }}>· {f.implied_pct}% implied</span>
              {f.best_book && <span style={{ color: "#fb7185", marginLeft: 8 }}>best @ {f.best_book}</span>}
            </div>
            <div style={{ marginTop: 6 }}>
              {f.reasons.map((r, j) => (
                <div key={j} style={{ fontSize: 9, color: "#666", marginBottom: 2 }}>• {r}</div>
              ))}
            </div>
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

export default function DiamondCode() {
  const [slate, setSlate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [filter, setFilter] = useState("all");
  const [view, setView] = useState("ai");
  const [dateOffset, setDateOffset] = useState(0); // 0 = today, 1 = tomorrow

  const [aiPicks, setAiPicks] = useState(null);

  const targetDate = (() => {
    const d = new Date();
    d.setDate(d.getDate() + dateOffset);
    return d.toISOString().slice(0, 10);
  })();

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

  // Auto-refresh every 30s when games are live (in-progress)
  useEffect(() => {
    const hasLive = allGames.some(g => g.abstract_state === "Live");
    if (!hasLive) return;
    const id = setInterval(() => { fetchSlate(); }, 30000);
    return () => clearInterval(id);
  }, [allGames]);

  // New-day detection: refetch when tab regains focus or once a minute if date has rolled over
  useEffect(() => {
    let lastDate = new Date().toISOString().slice(0, 10);
    const checkNewDay = () => {
      const today = new Date().toISOString().slice(0, 10);
      if (today !== lastDate) { lastDate = today; fetchSlate(); }
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
    <div style={{ minHeight: "100vh", background: "#050505", color: "#e0e0e0", fontFamily: "monospace", padding: "24px 16px", maxWidth: 860, margin: "0 auto" }}>

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
          <div style={{ color: "#ff3b3b", fontSize: 10 }}>⚠ Backend offline — make sure uvicorn is running</div>
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
