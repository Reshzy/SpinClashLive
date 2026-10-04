import { remainingMs, formatCountdown } from "../state/clock";
import { rankMoves, type BoardSnapshot } from "../state/ranks";
import { bonusLabel, safeText } from "../state/sanitize";
import { STATUS_COPY, type OverlayState, type SnapshotData } from "../state/types";

let previousBoard: BoardSnapshot | null = null;
let lastCeremonyId = "";
let ceremonyShownAt = 0;

export function scaleStage(stage: HTMLElement): void {
  const scale = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
  stage.style.transform = `scale(${scale})`;
}

export function renderOverlay(state: OverlayState): void {
  const data = state.snapshot?.data;
  const connection = document.getElementById("connection");
  const status = document.getElementById("status");
  const countdown = document.getElementById("countdown");
  const roundLabel = document.getElementById("round-label");
  const simBanner = document.getElementById("sim-banner");
  const bonusBanner = document.getElementById("bonus-banner");
  const empty = document.getElementById("empty-picks");
  const award = document.getElementById("award-status");
  const help = document.getElementById("help");
  const stage = document.getElementById("stage");
  if (!connection || !status || !countdown || !roundLabel || !simBanner || !bonusBanner || !empty || !award || !help || !stage) {
    return;
  }

  connection.textContent =
    state.connection === "connecting"
      ? "Awaiting connection"
      : state.connection === "recovering"
        ? "Recovering connection"
        : "Live";
  connection.className = `pill ${state.connection === "live" ? "live" : state.connection}`;

  if (!data) {
    status.textContent = state.connection === "recovering" ? "Recovering connection" : "Awaiting connection";
    return;
  }

  const roundState = data.state;
  status.textContent = STATUS_COPY[roundState] ?? roundState;
  roundLabel.textContent = data.round_number ? `Round ${data.round_number}` : "Round —";
  simBanner.hidden = data.source_mode !== "simulation";

  const remaining = remainingMs(data.closes_at, state.clockOffsetMs);
  countdown.textContent = roundState === "open" || roundState === "draining" ? formatCountdown(remaining) : "";

  const bonus = bonusLabel(data.rules.bonus);
  bonusBanner.hidden = !bonus;
  bonusBanner.textContent = bonus;

  const rewards = data.rules.rewards;
  for (const color of ["red", "gold", "green"] as const) {
    const rewardNode = document.querySelector(`[data-reward="${color}"]`);
    const countNode = document.querySelector(`[data-count="${color}"]`);
    const namesNode = document.querySelector(`[data-names="${color}"]`);
    if (rewardNode) {
      rewardNode.textContent = `+${rewards[color] ?? 0}`;
    }
    if (countNode) {
      countNode.textContent = String(data.counts[color] ?? 0);
    }
    if (namesNode) {
      namesNode.replaceChildren();
      for (const player of (data.recent_players[color] ?? []).slice(0, 10)) {
        const item = document.createElement("li");
        item.textContent = safeText(player.name, 22);
        namesNode.append(item);
      }
    }
  }

  const totalPicks = (data.counts.red ?? 0) + (data.counts.gold ?? 0) + (data.counts.green ?? 0);
  empty.hidden = !(roundState === "open" && totalPicks === 0);
  empty.textContent = "No picks yet";

  if (data.award_status === "pending") {
    award.hidden = false;
    award.textContent = "Updating scores";
  } else if (data.award_status === "committed") {
    award.hidden = false;
    award.textContent = "Points earned";
  } else if (data.award_status === "cancelled") {
    award.hidden = false;
    award.textContent = "Round cancelled";
  } else {
    award.hidden = true;
  }

  const history = document.getElementById("history");
  if (history) {
    history.replaceChildren();
    for (const color of data.recent_results.slice(0, 20)) {
      const chip = document.createElement("span");
      chip.className = `chip ${color}`;
      chip.title = color;
      history.append(chip);
    }
  }

  renderBoard(data.leaderboard);
  renderSpotlight(data);
  help.textContent = "Type !red / !gold / !green in chat";

  const goldWin = data.animation_plan?.target_color === "gold" && ["result", "settling", "settled"].includes(roundState);
  stage.classList.toggle("result-gold", goldWin);
}

function renderBoard(leaderboard: SnapshotData["leaderboard"]): void {
  const title = document.getElementById("board-title");
  const status = document.getElementById("board-status");
  const list = document.getElementById("board-list");
  if (!title || !status || !list) {
    return;
  }
  const next: BoardSnapshot = {
    scope: leaderboard.scope,
    periodId: leaderboard.period_id,
    entries: leaderboard.entries.map((entry) => ({ rank: entry.rank, player_id: entry.player_id })),
  };
  const moves = rankMoves(previousBoard, next);
  const moveById = new Map(moves.map((move) => [move.playerId, move.direction]));
  previousBoard = next;
  title.textContent = leaderboard.label || leaderboard.scope;
  const statusLabel = leaderboard.status && leaderboard.status !== "open" ? leaderboard.status : "";
  status.textContent = statusLabel;
  list.replaceChildren();
  for (const entry of leaderboard.entries.slice(0, 10)) {
    const item = document.createElement("li");
    const rank = document.createElement("span");
    rank.textContent = String(entry.rank);
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = safeText(entry.display_name, 18);
    const points = document.createElement("span");
    points.textContent = String(entry.points);
    const arrow = document.createElement("span");
    const direction = moveById.get(entry.player_id) ?? "none";
    arrow.className = `arrow ${direction}`;
    arrow.textContent = direction === "up" ? "▲" : direction === "down" ? "▼" : "";
    item.append(rank, name, points, arrow);
    list.append(item);
  }
}

function renderSpotlight(data: SnapshotData): void {
  const lookupRoot = document.getElementById("lookup");
  const ceremonyRoot = document.getElementById("ceremony");
  if (!lookupRoot || !ceremonyRoot) {
    return;
  }
  const lookup = (data.lookup ?? [])[0];
  if (lookup && typeof lookup === "object") {
    const expires = Number((lookup as { expires_at?: number }).expires_at ?? 0);
    if (!expires || expires * 1000 > Date.now()) {
      lookupRoot.hidden = false;
      lookupRoot.replaceChildren();
      const heading = document.createElement("h2");
      heading.textContent = "Player lookup";
      const name = document.createElement("p");
      name.textContent = safeText((lookup as { display_name?: string }).display_name, 22);
      lookupRoot.append(heading, name);
    } else {
      lookupRoot.hidden = true;
    }
  } else {
    lookupRoot.hidden = true;
  }

  const ceremony = data.ceremony;
  if (ceremony && typeof ceremony === "object") {
    const id = String((ceremony as { id?: string }).id ?? "");
    if (id && id !== lastCeremonyId) {
      lastCeremonyId = id;
      ceremonyShownAt = Date.now();
    }
    if (Date.now() - ceremonyShownAt < 20_000) {
      ceremonyRoot.hidden = false;
      ceremonyRoot.replaceChildren();
      const heading = document.createElement("h2");
      heading.textContent = "Champion";
      const title = document.createElement("p");
      title.textContent = safeText((ceremony as { title?: string }).title, 40);
      const name = document.createElement("p");
      name.textContent = safeText((ceremony as { display_name?: string }).display_name, 22);
      ceremonyRoot.append(heading, title, name);
      return;
    }
  }
  ceremonyRoot.hidden = true;
}
