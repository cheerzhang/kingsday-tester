const fs = require('fs');
const path = require('path');
const { RUNTIME_DIR, loadJson } = require('./gameLogic');

const CURRENT_GAME_PATH = path.join(RUNTIME_DIR, 'current_game.json');

function ensureRuntimeDir() {
  fs.mkdirSync(RUNTIME_DIR, { recursive: true });
}

function gamestatePath(roleId) {
  ensureRuntimeDir();
  return path.join(RUNTIME_DIR, `${roleId}_gamestate.json`);
}

function loadGamestate(roleId) {
  return loadJson(gamestatePath(roleId), { role_id: roleId, counters: {} });
}

function getCounter(gs, key) {
  const counters = gs && typeof gs === 'object' && !Array.isArray(gs) ? gs.counters : null;
  if (!counters || typeof counters !== 'object' || Array.isArray(counters)) return 0;
  const n = Number.parseInt(counters[key] || 0, 10);
  return Number.isFinite(n) ? n : 0;
}

function loadCurrentGame() {
  ensureRuntimeDir();
  return loadJson(CURRENT_GAME_PATH, { players: [] });
}

function wearNOrangeItems(roleId, params) {
  const n = Number.parseInt((params || {}).n || 0, 10) || 0;
  const gs = loadGamestate(roleId);
  return getCounter(gs, 'orange_worn') >= n;
}

function takeNPhoto(roleId, params) {
  const n = Number.parseInt((params || {}).n || 0, 10) || 0;
  const gs = loadGamestate(roleId);
  const photo = getCounter(gs, 'photo');
  if (photo < n) return false;

  const counters = gs.counters;
  if (!counters || typeof counters !== 'object' || Array.isArray(counters)) return false;
  const targets = Array.isArray(counters.photo_targets) ? counters.photo_targets : [];
  const uniq = new Set(targets.filter((t) => typeof t === 'string' && t));

  const cur = loadCurrentGame();
  const players = Array.isArray(cur.players) ? cur.players : [];
  const needUnique = players.length <= 3 ? 2 : 3;
  return uniq.size >= needUnique;
}

function performNTimes(roleId, params) {
  const n = Number.parseInt((params || {}).n || 0, 10) || 0;
  return getCounter(loadGamestate(roleId), 'perform') >= n;
}

function volunteerHelpNTypes(roleId, params) {
  const n = Number.parseInt((params || {}).n || 0, 10) || 0;
  const gs = loadGamestate(roleId);
  const counters = gs.counters;
  if (!counters || typeof counters !== 'object' || Array.isArray(counters)) return false;
  const types = Array.isArray(counters.help_types) ? counters.help_types : [];
  const uniq = new Set(types.filter((t) => typeof t === 'string' && t));
  return uniq.size >= n;
}

function persistProgressDetail(roleId, gs, detail) {
  gs.progress_detail = detail;
  try {
    fs.writeFileSync(gamestatePath(roleId), JSON.stringify(gs, null, 2), 'utf-8');
  } catch (_) {
    // ignore
  }
}

function vendorTradeDynamic(roleId) {
  const cur = loadCurrentGame();
  const players = Array.isArray(cur.players) ? cur.players : [];
  if (!players.includes(roleId)) return false;

  const N = Math.max(0, players.length - 1);
  const targetTrades = N;
  const targetUnique = Math.max(0, N - 1);

  const gs = loadGamestate(roleId);
  const counters = gs.counters && typeof gs.counters === 'object' && !Array.isArray(gs.counters) ? gs.counters : {};
  gs.counters = counters;

  const tradesDone = Number.parseInt(counters.trades_done || 0, 10) || 0;
  const partners = Array.isArray(counters.trade_partners) ? counters.trade_partners : [];
  const uniqueCount = new Set(partners.filter((p) => typeof p === 'string' && p && p !== roleId)).size;

  persistProgressDetail(roleId, gs, {
    target_trades: targetTrades,
    target_unique_partners: targetUnique,
    trades_done: tradesDone,
    unique_partners: uniqueCount,
  });

  return tradesDone >= targetTrades && uniqueCount >= targetUnique;
}

function foodVendorTradeDynamic(roleId) {
  const cur = loadCurrentGame();
  const players = Array.isArray(cur.players) ? cur.players : [];
  if (!players.includes(roleId)) return false;

  const N = Math.max(0, players.length - 1);
  const targetTrades = N;
  const targetUnique = Math.max(0, N - 2);

  const gs = loadGamestate(roleId);
  const counters = gs.counters && typeof gs.counters === 'object' && !Array.isArray(gs.counters) ? gs.counters : {};
  gs.counters = counters;

  const tradesDone = Number.parseInt(counters.trades_done || 0, 10) || 0;
  const partners = Array.isArray(counters.trade_partners) ? counters.trade_partners : [];
  const uniqueCount = new Set(partners.filter((p) => typeof p === 'string' && p && p !== roleId)).size;

  persistProgressDetail(roleId, gs, {
    target_trades: targetTrades,
    target_unique_partners: targetUnique,
    trades_done: tradesDone,
    unique_partners: uniqueCount,
  });

  return tradesDone >= targetTrades && uniqueCount >= targetUnique;
}

function foodVendorOfferGoal(roleId, params) {
  const n = Number.parseInt((params || {}).n || 0, 10) || 0;
  const gs = loadGamestate(roleId);
  const counters = gs.counters;
  if (!counters || typeof counters !== 'object' || Array.isArray(counters)) return false;

  const offerSuccess = Number.parseInt(counters.feed_successes || 0, 10) || 0;
  const eaters = Array.isArray(counters.feed_eaters) ? counters.feed_eaters : [];
  const uniq = new Set(eaters.filter((p) => typeof p === 'string' && p && p !== roleId));
  return offerSuccess >= n && uniq.size >= n;
}

const VICTORY_REGISTRY = {
  wear_n_orange_items: wearNOrangeItems,
  take_n_photo: takeNPhoto,
  vendor_trade_dynamic: vendorTradeDynamic,
  food_vendor_trade_dynamic: foodVendorTradeDynamic,
  food_vendor_offer_goal: foodVendorOfferGoal,
  perform_n_times: performNTimes,
  volunteer_help_n_types: volunteerHelpNTypes,
};

module.exports = {
  CURRENT_GAME_PATH,
  gamestatePath,
  loadGamestate,
  getCounter,
  loadCurrentGame,
  wearNOrangeItems,
  takeNPhoto,
  performNTimes,
  volunteerHelpNTypes,
  vendorTradeDynamic,
  foodVendorTradeDynamic,
  foodVendorOfferGoal,
  VICTORY_REGISTRY,
};
