const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const ROLES_DIR = path.join(ROOT, 'data', 'roles');
const RUNTIME_DIR = path.join(ROOT, 'data', 'runtime');
const CURRENT_GAME_PATH = path.join(RUNTIME_DIR, 'current_game.json');
const GLOBAL_DEFS_PATH = path.join(ROOT, 'data', 'global_defs.json');

const REQUIRED_ROLE_IDS = new Set(['role_finn', 'role_tourist']);
const VENDOR_ROLE_ID = 'role_vendor';
const FOOD_VENDOR_ROLE_ID = 'role_food_vendor';

function ensureDirs() {
  fs.mkdirSync(ROLES_DIR, { recursive: true });
  fs.mkdirSync(RUNTIME_DIR, { recursive: true });
}

function loadJson(filePath, fallback) {
  try {
    const raw = fs.readFileSync(filePath, 'utf-8');
    const obj = JSON.parse(raw);
    return obj && typeof obj === 'object' && !Array.isArray(obj) ? obj : fallback;
  } catch (_) {
    return fallback;
  }
}

function saveJson(filePath, obj) {
  fs.writeFileSync(filePath, JSON.stringify(obj, null, 2), 'utf-8');
}

function loadTradeDefaults() {
  const obj = loadJson(GLOBAL_DEFS_PATH, {});
  const td = obj.trade_defaults;
  if (!td || typeof td !== 'object' || Array.isArray(td)) {
    return { price_mod: 1, price_override: { product: 1, orange_product: 2 } };
  }
  return td;
}

function roleGamestatePath(roleId) {
  ensureDirs();
  return path.join(RUNTIME_DIR, `${roleId}_gamestate.json`);
}

function listRoleFiles() {
  ensureDirs();
  return fs.readdirSync(ROLES_DIR).filter((f) => f.endsWith('.json')).sort();
}

function loadRoleByFile(filename) {
  return loadJson(path.join(ROLES_DIR, filename), {});
}

function loadAllRolesMin() {
  const roles = [];
  for (const fn of listRoleFiles()) {
    const obj = loadRoleByFile(fn);
    const rid = String(obj.id || '').trim();
    const name = String(obj.name || '').trim();
    const initNumber = obj.init_number;

    if (!rid || !name || !initNumber || typeof initNumber !== 'object' || Array.isArray(initNumber)) {
      continue;
    }

    roles.push({
      id: rid,
      name,
      file: fn,
      init_number: initNumber,
    });
  }
  return roles;
}

function initGameRuntime(selectedRoleIds) {
  ensureDirs();

  const chosen = [...new Set(Array.isArray(selectedRoleIds) ? selectedRoleIds : [])];
  for (const req of REQUIRED_ROLE_IDS) {
    if (!chosen.includes(req)) {
      chosen.unshift(req);
    }
  }

  const roleMap = new Map(loadAllRolesMin().map((r) => [r.id, r]));

  for (const rid of chosen) {
    const role = roleMap.get(rid);
    if (!role) continue;

    const status = {};
    for (const [k, cfg] of Object.entries(role.init_number || {})) {
      if (cfg && typeof cfg === 'object' && !Array.isArray(cfg)) {
        const n = Number.parseInt(cfg.number, 10);
        status[k] = Number.isFinite(n) ? n : 0;
      }
    }
    if (!Object.prototype.hasOwnProperty.call(status, 'progress')) {
      status.progress = 0;
    }

    const gs = { role_id: rid, status };

    if (rid === VENDOR_ROLE_ID || rid === FOOD_VENDOR_ROLE_ID) {
      gs.counters = { trades_done: 0, trade_partners: [] };
      gs.progress_detail = {
        target_trades: 0,
        target_unique_partners: 0,
        trades_done: 0,
        unique_partners: 0,
      };
      const defaults = loadTradeDefaults();
      const baseState = {
        price_mod: Number.parseInt(defaults.price_mod, 10) || 1,
        price_override: { ...(defaults.price_override || {}) },
      };
      const tsi = role.trade_state_init;
      if (tsi && typeof tsi === 'object' && !Array.isArray(tsi)) {
        Object.assign(baseState, JSON.parse(JSON.stringify(tsi)));
      }
      gs.trade_state = baseState;
    }

    saveJson(roleGamestatePath(rid), gs);
  }

  const defaults = loadTradeDefaults();
  const cur = {
    players: chosen,
    game_over: false,
    game_over_reason: '',
    events_drawn: [],
    rounds_completed: 0,
    global_trade_state: { price_mod: Number.parseInt(defaults.price_mod, 10) || 1 },
  };
  saveJson(CURRENT_GAME_PATH, cur);

  return chosen;
}

function loadCurrentGame() {
  ensureDirs();
  return loadJson(CURRENT_GAME_PATH, {
    players: [],
    game_over: false,
    game_over_reason: '',
    rounds_completed: 0,
  });
}

function isGameOver() {
  return Boolean(loadCurrentGame().game_over);
}

function loadPlayerGamestate(roleId) {
  return loadJson(roleGamestatePath(roleId), { role_id: roleId, status: {} });
}

function resetRuntime() {
  ensureDirs();
  for (const fn of fs.readdirSync(RUNTIME_DIR)) {
    if (fn.endsWith('_gamestate.json') || fn === 'current_game.json') {
      try {
        fs.unlinkSync(path.join(RUNTIME_DIR, fn));
      } catch (_) {
        // ignore
      }
    }
  }
}

module.exports = {
  ROOT,
  ROLES_DIR,
  RUNTIME_DIR,
  CURRENT_GAME_PATH,
  GLOBAL_DEFS_PATH,
  REQUIRED_ROLE_IDS,
  VENDOR_ROLE_ID,
  FOOD_VENDOR_ROLE_ID,
  roleGamestatePath,
  listRoleFiles,
  loadRoleByFile,
  loadAllRolesMin,
  initGameRuntime,
  loadCurrentGame,
  isGameOver,
  loadPlayerGamestate,
  resetRuntime,
  loadJson,
  saveJson,
};
