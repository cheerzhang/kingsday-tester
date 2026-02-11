const fs = require('fs');
const path = require('path');
const {
  ROOT,
  ROLES_DIR,
  RUNTIME_DIR,
  loadJson,
  saveJson,
} = require('./gameLogic');

const WINRATE_PATH = path.join(RUNTIME_DIR, 'winrate.json');

function rolePath(roleId) {
  return path.join(ROLES_DIR, `${roleId}.json`);
}

function loadRoleById(roleId) {
  if (!fs.existsSync(ROLES_DIR)) {
    return {};
  }
  for (const fn of fs.readdirSync(ROLES_DIR)) {
    if (!fn.endsWith('.json')) continue;
    const obj = loadJson(path.join(ROLES_DIR, fn), {});
    if (obj.id === roleId) {
      return obj;
    }
  }
  return {};
}

function gamestatePath(roleId) {
  return path.join(RUNTIME_DIR, `${roleId}_gamestate.json`);
}

function loadGamestate(roleId) {
  return loadJson(gamestatePath(roleId), { role_id: roleId, status: {} });
}

function canPayCost(status, resource, delta) {
  if (!status || typeof status !== 'object' || Array.isArray(status)) return false;
  const cur = Number.parseInt(status[resource] || 0, 10);
  const d = Number.parseInt(delta, 10);
  if (!Number.isFinite(cur) || !Number.isFinite(d)) return false;
  return cur + d >= 0;
}

function normalizeCostOption(opt) {
  if (!opt || typeof opt !== 'object' || Array.isArray(opt)) return null;

  if (Array.isArray(opt.costs)) {
    const costs = [];
    for (const c of opt.costs) {
      if (!c || typeof c !== 'object' || Array.isArray(c)) continue;
      const res = c.resource;
      const delta = Number.parseInt(c.delta, 10);
      if (!res || !Number.isFinite(delta)) continue;
      costs.push({ resource: String(res), delta });
    }
    if (!costs.length) return null;
    return { costs };
  }

  const res = opt.resource;
  const delta = Number.parseInt(opt.delta, 10);
  if (!res || !Number.isFinite(delta)) return null;
  return { costs: [{ resource: String(res), delta }] };
}

function checkDrawCardEligibility(roleObj, gamestateObj) {
  const dc = roleObj && typeof roleObj === 'object' ? roleObj.draw_card_cost : null;
  if (!dc || typeof dc !== 'object' || Array.isArray(dc)) {
    return [false, []];
  }

  const options = dc.options;
  if (!Array.isArray(options) || !options.length) {
    return [false, []];
  }

  const statusRaw = gamestateObj && typeof gamestateObj === 'object' ? gamestateObj.status : {};
  const status = statusRaw && typeof statusRaw === 'object' && !Array.isArray(statusRaw) ? statusRaw : {};

  const payable = [];
  for (const opt of options) {
    const norm = normalizeCostOption(opt);
    if (!norm) continue;
    const costs = norm.costs || [];
    if (costs.every((c) => canPayCost(status, c.resource, c.delta))) {
      payable.push(norm);
    }
  }

  return [payable.length > 0, payable];
}

function saveGamestate(roleId, gamestateObj) {
  fs.mkdirSync(RUNTIME_DIR, { recursive: true });
  saveJson(gamestatePath(roleId), gamestateObj);
}

function applyCostOption(roleId, option) {
  const gs = loadGamestate(roleId);
  if (!gs.status || typeof gs.status !== 'object' || Array.isArray(gs.status)) {
    gs.status = {};
  }
  const st = gs.status;

  const costs = Array.isArray(option.costs) ? option.costs : null;
  if (costs && costs.length) {
    for (const c of costs) {
      if (!c || typeof c !== 'object' || Array.isArray(c)) continue;
      const res = String(c.resource || '').trim();
      const delta = Number.parseInt(c.delta || 0, 10);
      if (!res || !Number.isFinite(delta)) continue;
      const cur = Number.parseInt(st[res] || 0, 10);
      const next = (Number.isFinite(cur) ? cur : 0) + delta;
      st[res] = Math.max(0, next);
    }
  } else {
    const res = String(option.resource || '').trim();
    const delta = Number.parseInt(option.delta || 0, 10);
    if (res && Number.isFinite(delta)) {
      const cur = Number.parseInt(st[res] || 0, 10);
      const next = (Number.isFinite(cur) ? cur : 0) + delta;
      st[res] = Math.max(0, next);
    }
  }

  saveGamestate(roleId, gs);
  return gs;
}

function getDrawCostConfig(roleObj) {
  const dc = roleObj && typeof roleObj === 'object' ? roleObj.draw_card_cost : null;
  if (!dc || typeof dc !== 'object' || Array.isArray(dc)) {
    return ['THEN', []];
  }

  let logic = String(dc.logic || 'THEN').toUpperCase();
  if (!['THEN', 'OR'].includes(logic)) {
    logic = 'THEN';
  }

  const opts = Array.isArray(dc.options) ? dc.options : [];
  const out = [];
  for (const o of opts) {
    const norm = normalizeCostOption(o);
    if (norm) out.push(norm);
  }
  return [logic, out];
}

function updateWinrate(players, winners, draws = null, rounds = null) {
  const key = [...players].sort().join('|');
  const data = loadJson(WINRATE_PATH, { total_games: 0, by_player_set: {} });

  data.total_games = Number.parseInt(data.total_games || 0, 10) + 1;

  if (!data.by_player_set || typeof data.by_player_set !== 'object' || Array.isArray(data.by_player_set)) {
    data.by_player_set = {};
  }

  if (!data.by_player_set[key]) {
    data.by_player_set[key] = {
      games: 0,
      wins: {},
      draws_total: 0,
      rounds_total: 0,
      avg_draws: 0,
      avg_rounds: 0,
    };
  }

  const rec = data.by_player_set[key];
  rec.games = Number.parseInt(rec.games || 0, 10) + 1;

  for (const w of winners || []) {
    rec.wins[w] = Number.parseInt(rec.wins[w] || 0, 10) + 1;
  }

  if (draws !== null && draws !== undefined) {
    const d = Number.parseInt(draws, 10);
    if (Number.isFinite(d)) {
      rec.draws_total = Number.parseInt(rec.draws_total || 0, 10) + d;
    }
  }

  if (rounds !== null && rounds !== undefined) {
    const r = Number.parseInt(rounds, 10);
    if (Number.isFinite(r)) {
      rec.rounds_total = Number.parseInt(rec.rounds_total || 0, 10) + r;
    }
  }

  const games = Math.max(1, Number.parseInt(rec.games || 0, 10));
  rec.avg_draws = Math.round((Number.parseInt(rec.draws_total || 0, 10) / games) * 100) / 100;
  rec.avg_rounds = Math.round((Number.parseInt(rec.rounds_total || 0, 10) / games) * 100) / 100;

  fs.mkdirSync(RUNTIME_DIR, { recursive: true });
  saveJson(WINRATE_PATH, data);
}

module.exports = {
  ROOT,
  ROLES_DIR,
  RUNTIME_DIR,
  WINRATE_PATH,
  rolePath,
  loadRoleById,
  gamestatePath,
  loadGamestate,
  canPayCost,
  checkDrawCardEligibility,
  saveGamestate,
  applyCostOption,
  getDrawCostConfig,
  updateWinrate,
};
