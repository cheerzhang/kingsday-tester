'use strict';
const E = window.Kingsday;
const app = document.getElementById('app');
const sheet = document.getElementById('sheet');
const sheetBody = document.getElementById('sheet-content');
const STORE = 'kingsday-adventure-v1';
const ids = Object.keys(E.roles);
const crown = '<svg class="crown" viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M6 12 14 19 20 7 26 19 34 12 30 31H10Z" stroke="currentColor" stroke-width="2" fill="currentColor" fill-opacity=".14"/><path d="M11 35H29" stroke="currentColor" stroke-width="2"/><circle cx="20" cy="24" r="2" fill="currentColor"/></svg>';
const aliases = {role_finn:'THE ORANGE DREAMER',role_tourist:'THE MEMORY KEEPER',role_vendor:'THE DEAL MAKER',role_food_vendor:'THE WAFFLE MAKER',role_performer:'THE STREET ARTIST',role_volunteer:'THE HELPING HAND'};
const goals = {role_finn:'穿戴三件橙色物品',role_tourist:'完成三次有效拍照',role_vendor:'完成三次有效交易',role_food_vendor:'成功供餐五次',role_performer:'完成三次成功表演',role_volunteer:'成功帮助他人三次'};
const symbols = ['♛','♛','♛','♛','✦','✦','✦','✦','♫','♫','♫','♫','◉','◉','◉','◉','❋','❋','❋','❋'];
const eventNames = ['橙色王冠','有点不合身','橙色围巾','满街橙色','人潮拥挤','快闪摊位','即兴交换','看起来很有趣','即兴演出','一起上台？','掌声不停','被拉上舞台','镜头无处不在','帮我拍张照？','悄悄入镜','完美一拍','一起吃点东西','闻起来真香','长长的队伍','最后一份'];
const globals = ['抽卡者获得 1 件橙色物品。','好奇心最低的玩家及抽卡者，好奇心 +1。','抽卡者获得 1 件橙色物品。','所有玩家好奇心 +1。','抽卡者体力 −1，好奇心 +1。','抽卡者获得 1 件普通物品。','选择另一位玩家，触发角色专属交换。','选择一位玩家，对方好奇心 +1。','所有玩家可选择围观，围观者体力 +2。','抽卡者好奇心 +1。','抽卡者体力 +1，好奇心 +1。','选择一位玩家，对方普通物品 +1。','所有玩家可选择参与，参与者好奇心 +1。','选择另一位玩家，对方好奇心 +1。','选择另一位玩家，对方好奇心 +2。','抽卡者金钱 +1。','选择另一位玩家，对方普通物品 +2。','抽卡者支付 1 金钱，获得 1 橙色物品。','选择另一位玩家，你和对方体力 +2。','所有玩家金钱 +1，Finn 额外体力 +1。'];
const resourceNames = {curiosity:'好奇心',money:'金钱',stamina:'体力',product:'普通物品',orange_product:'橙色物品',orange_wear_product:'已穿戴',progress:'进度'};
const resourceIcons = {curiosity:'🔍',money:'💰',stamina:'♥',product:'📦',orange_product:'♛',orange_wear_product:'♔'};
const resourceShort = {curiosity:'好奇',money:'金钱',stamina:'体力',product:'物品',orange_product:'橙色',orange_wear_product:'穿戴'};
let config = {total:6,humans:1};
let people = [], viewer = null, currentScreen = 'lobby', timer = null, speed = 1, feed = '', lastAction = '', drawReady = false;
let saved = null;
try { saved = JSON.parse(localStorage.getItem(STORE)); } catch (_) {}
function esc(s) { return String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function art(id, extra='') { const i = ids.indexOf(id); return `<div class="portrait ${extra}" style="--px:${(i%3)*50}%;--py:${i<3?0:100}%" role="img" aria-label="${esc(E.roles[id]?.name)}角色插画"></div>`; }
function name(id) { return E.roles[id]?.name || ''; }
function person(id) { const i = people.indexOf(id); return i < 0 ? 'BOT' : people.length === 1 ? '你' : `玩家 ${i+1}`; }
function text(s) { let t=String(s||''); for (const [a,b] of Object.entries(resourceNames).sort((a,b)=>b[0].length-a[0].length)) t=t.replaceAll(a,b); return t.replaceAll('Watch','围观').replaceAll('photo','拍照').replaceAll('buy','代买').replaceAll('recover','恢复').replaceAll('help','帮助'); }
function costs(def) { return def.drawCost.options.map(c=>c.map(([r,n])=>`${resourceNames[r]} ${n}`).join(' + ')).join(def.drawCost.logic==='OR'?' 或 ':'，不足时 '); }
function stop() { clearTimeout(timer); timer=null; }
function notify(msg) { const el=document.getElementById('notice'); el.textContent=msg; el.classList.add('show'); setTimeout(()=>el.classList.remove('show'),3200); }
function showSheet(html) { stop(); sheetBody.innerHTML=html; sheet.showModal(); }
sheet.querySelector('.close').onclick=()=>sheet.close();
sheet.addEventListener('close',()=>{if(currentScreen==='game') schedule();});
sheet.addEventListener('click',e=>{if(e.target===sheet) {const r=sheet.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom) sheet.close();}});
function persist() { try { localStorage.setItem(STORE,JSON.stringify({version:1,people,viewer,game:E.save(),feed,config})); } catch (_) {} }
function help() { showSheet(`<span class="eyebrow">HOW TO PLAY</span><h2>你的国王节，由你决定</h2><p>每人随机获得一个不同角色。轮到你时，抽一张事件卡或使用角色技能，最先完成角色目标的玩家获胜。20 张事件卡抽完仍无人达成目标，则本局没有赢家。</p><h3>你的回合</h3><p>抽卡需要支付角色指定的资源。技能也有自己的条件，点击角色卡旁的“角色说明”可以查看。其他人找你交易、拍照或邀请你围观时，游戏会停下来让你回应。</p><h3>和谁一起玩</h3><p>一名真人即可与 Bot 对局。也支持同一部手机上 2–6 名真人轮流操作，剩余席位由 Bot 补齐。交接时会遮住角色卡。当前版本不提供跨手机联网房间。</p><h3>资源</h3><p>🔍 好奇心 · 💰 金钱 · ♥ 体力\n📦 普通物品 · ♛ 橙色物品 · ♔ 已穿戴橙色</p><p>对局会自动保存到本机浏览器。原始角色规则、资源结算和 20 张事件均来自你的逻辑版本。</p>`); }
function lobby() {
  stop(); currentScreen='lobby';
  try { saved=JSON.parse(localStorage.getItem(STORE)); } catch (_) {saved=null;}
  app.innerHTML=`<header class="brand"><span>${crown} KINGSDAY</span><button class="circle-btn" id="help" aria-label="玩法说明">?</button></header>
  <section class="lobby"><div class="eyebrow overline">AN ORANGE LITTLE ADVENTURE</div><h1>橙色奇遇</h1><p class="tagline">一座城市 · 六种身份 · 你的国王节</p>
  <div class="fan" aria-label="六种角色，随机抽取"><div class="fan-card">${art('role_tourist')}<div class="card-label">游客</div></div><div class="fan-card">${art('role_finn')}<div class="card-label">Finn</div></div><div class="fan-card">${art('role_performer')}<div class="card-label">表演者</div></div></div>
  <div class="room"><div class="setting"><strong>这桌几位？</strong><div class="stepper"><button id="less-total" aria-label="减少总人数" ${config.total<=2?'disabled':''}>−</button><b>${config.total}</b><button id="more-total" aria-label="增加总人数" ${config.total>=6?'disabled':''}>+</button></div></div>
  <div class="setting"><strong>真人玩家</strong><div class="stepper"><button id="less-human" aria-label="减少真人" ${config.humans<=1?'disabled':''}>−</button><b>${config.humans}</b><button id="more-human" aria-label="增加真人" ${config.humans>=config.total?'disabled':''}>+</button></div></div><p class="room-note">${config.humans===1?'你将随机抽取一个角色':config.humans+' 位朋友共用手机，轮流操作'} · ${config.total-config.humans} 位 Bot 入座</p></div>
  <button class="primary wide" id="new-game">抽取我的角色 <span aria-hidden="true">↗</span></button>
  ${saved?.version===1&&!saved.game?.gameOver?'<button class="secondary wide resume" id="resume">继续上次的奇遇</button>':''}
  <div class="lobby-foot">20 张事件卡 · 随机身份 · 各自的胜利目标</div></section>`;
  document.getElementById('help').onclick=help;
  for(const [id,key,delta] of [['less-total','total',-1],['more-total','total',1],['less-human','humans',-1],['more-human','humans',1]]) document.getElementById(id).onclick=()=>{config[key]+=delta;config.humans=Math.min(config.humans,config.total);lobby();};
  document.getElementById('new-game').onclick=()=>{
    if(saved?.game&&!saved.game.gameOver){showSheet('<h2>开启一场新奇遇？</h2><p>这会替换本机保存的上一局。</p><button class="primary wide" id="confirm-new">开始新局</button>');document.getElementById('confirm-new').onclick=()=>{sheet.close();startDraw();};}else startDraw();
  };
  const resume=document.getElementById('resume'); if(resume)resume.onclick=()=>{try{people=saved.people;config=saved.config;viewer=people.length>1?null:saved.viewer;feed=saved.feed||'';E.restore(saved.game);currentScreen='game';renderGame();}catch(_){notify('这份存档无法读取，请开始新局。');}};
}
function startDraw() {
  stop(); currentScreen='draw';drawReady=false;
  const shuffled=[...ids]; for(let i=shuffled.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[shuffled[i],shuffled[j]]=[shuffled[j],shuffled[i]];}
  const seats=shuffled.slice(0,config.total);people=seats.slice(0,config.humans);viewer=people[0];feed='国王节开场了。看看今天你会遇到谁。';E.start(seats);
  app.innerHTML=`<section class="draw-screen"><div class="eyebrow">YOUR STORY STARTS HERE</div><h1>今天，你会是谁？</h1><p>六种身份，各有一场小小的冒险。</p><button class="reveal-card card-back" id="flip" aria-label="翻开随机角色卡">${crown}<span>KINGSDAY</span><p>轻触翻开</p></button><p>角色随机分配 · 每局身份不重复</p></section>`;
  document.getElementById('flip').onclick=()=>{if(drawReady)return;drawReady=true;reveal();};
}
function reveal() {
  const def=E.roles[viewer];
  app.innerHTML=`<section class="draw-screen"><div class="eyebrow">${people.length>1?'PLAYER 01':'YOUR CHARACTER'}</div><h1>这就是你的角色</h1><div class="reveal-card">${art(viewer)}<h2>${esc(def.name)}</h2><span class="role-sub">${aliases[viewer]}</span><p>${esc(goals[viewer])}<br>即可赢得这场奇遇</p></div><p>${esc(def.skillDesc)}</p><button class="primary wide" id="enter">入座，开始奇遇</button></section>`;
  document.getElementById('enter').onclick=()=>{currentScreen='game';persist();renderGame();};
}
function playerSheet(id) {
  const p=E.snapshot().players.find(p=>p.roleId===id),def=E.roles[id];
  showSheet(`${art(id)}<span class="eyebrow">${aliases[id]}</span><h2>${esc(def.name)} <span class="badge">${person(id)}</span></h2><h3>胜利目标</h3><p>${esc(def.winDesc)}\n当前进度：${p.achieved} / ${p.goal}</p><h3>角色技能 · ${esc(def.skillName)}</h3><p>${esc(def.skillDesc)}</p><h3>抽卡代价</h3><p>${esc(costs(def))}</p><h3>资源</h3><p>${Object.keys(resourceIcons).map(k=>`${resourceIcons[k]} ${resourceNames[k]} ${p.status[k]||0}`).join('　')}</p>`);
}
function phasePrompt(s) {
  const ui=s.ui,actor=name(ui.actor||s.players[s.turnIndex].roleId);
  if(ui.mode==='TURN_CHOICE')return '轮到你了，选择今天的行动';
  if(ui.mode==='TURN_CONFIRM')return '这一回合已结算，准备交给下一位';
  if(ui.mode==='DRAW_COST_CHOICE')return '选择抽卡要支付的资源';
  if(ui.mode==='FINN_CONSENT')return `${actor} 想要一件橙色物品，你愿意给吗？`;
  if(ui.mode.includes('PHOTO_CONSENT')||ui.mode.includes('TOURIST_CONSENT'))return `${actor} 想给你拍照，你愿意吗？`;
  if(ui.mode==='TRADE_CONSENT'||ui.mode==='EVENT_CARD14_VENDOR_CONSENT')return `${actor} 向你出售${ui.item?.label||'物品'}${ui.price!=null?'，价格 '+ui.price+' 金钱':''}`;
  if(ui.mode==='VOL_CONSENT')return `${actor} 想帮助你，接受这份好意吗？`;
  if(ui.mode.includes('FOOD_DECIDE'))return `${actor} 正在供餐，要购买吗？`;
  if(ui.mode.includes('WATCH'))return `${actor} 邀请你围观，加入热闹吗？`;
  if(ui.mode.includes('PARTICIPATE'))return '大家都可以参加，你要加入吗？';
  if(ui.mode.includes('CONSENT'))return `${actor} 向你发出邀请，请作出选择`;
  if(ui.mode.includes('TARGET')||ui.mode==='TRADE_PARTNER')return '选择一位玩家，继续这段奇遇';
  if(ui.mode.includes('PAY')||ui.mode==='PERFORM_BENEFIT')return '选择你的支付方式';
  if(ui.mode.includes('TOGGLE'))return '要改变橙色物品的穿戴状态吗？';
  return '选择卡牌带给你的机会';
}
function actionLabel(a,owner) {
  let label=text(a.label).replace(name(owner)+' ','');
  if(a.action==='request_draw')return '抽取事件卡';
  if(a.action==='use_skill')return '发动角色技能';
  if(a.action==='next_turn')return '结束回合';
  if(a.action==='vol_type')label=label.replace('帮助类型 ','');
  return esc(label);
}
function stats(p) {return `<div class="stats">${Object.keys(resourceIcons).map(k=>`<div class="stat"><span>${resourceIcons[k]}<b>${p.status[k]||0}</b></span><small>${resourceShort[k]}</small></div>`).join('')}</div>`;}
function progress(p) {return `<div class="progress"><i style="width:${Math.min(100,p.achieved/p.goal*100)}%"></i></div>`;}
function renderGame() {
  stop(); const s=E.snapshot();if(!s)return lobby();
  if(s.gameOver)return result(s);
  if(people.includes(s.owner)&&people.length>1&&viewer!==s.owner)return pass(s.owner);
  currentScreen='game';const me=s.players.find(p=>p.roleId===viewer)||s.players.find(p=>people.includes(p.roleId));
  const mine=s.owner===viewer&&people.includes(s.owner);const turn=s.players[s.turnIndex];const event=s.currentEvent;const n=event?.no||0;
  app.innerHTML=`<header class="hud"><button class="circle-btn" id="menu" aria-label="游戏菜单">≡</button><div class="hud-center"><strong>KINGSDAY</strong><span>ROUND ${String(s.round).padStart(2,'0')} · 国王节</span></div><div class="deck-count" aria-label="剩余 ${s.deck.length} 张事件"><svg viewBox="0 0 24 26" fill="none"><rect x="7" y="2" width="14" height="19" rx="2" stroke="currentColor"/><path d="M3 6v17h14" stroke="currentColor"/><path d="m10 10 4 5 4-5" stroke="currentColor"/></svg>${s.deck.length}</div></header>
  <nav class="opponents" aria-label="其他玩家">${s.players.filter(p=>p.roleId!==viewer).map(p=>`<button class="opponent ${p.roleId===s.owner?'active':''}" data-player="${p.roleId}" aria-label="${name(p.roleId)}，${person(p.roleId)}，进度 ${p.achieved}/${p.goal}">${art(p.roleId)}<span class="name">${name(p.roleId)}</span><span class="bot-label">${person(p.roleId)} · ${p.achieved}/${p.goal}</span>${progress(p)}</button>`).join('')}</nav>
  <div class="phase-banner ${mine?'':'waiting'}"><span class="dot"></span>${mine?(turn.roleId===viewer?'你的回合':'有人在等你的回应'):`${esc(name(s.owner))} 正在行动`}</div>
  <section class="tableau" aria-label="桌面事件">${event?`<article class="event-card" data-event="${event.id}"><div class="event-top"><span>${esc(turn.name)} 抽到的事件</span><span>No. ${String(n).padStart(2,'0')}</span></div><span class="event-symbol" aria-hidden="true">${symbols[n-1]}</span><h2>${eventNames[n-1]}</h2><p>${globals[n-1]}</p><button class="event-detail" id="event-info">查看角色效果 ↗</button></article>`:`<article class="event-card empty-event">${crown}<h2>街角，会有什么奇遇？</h2><p>抽一张事件，或用你的技能改变局面。</p></article>`}</section>
  <article class="my-card" aria-label="我的角色卡"><div class="my-top">${art(me.roleId)}<div class="my-info"><div class="eyebrow">${person(me.roleId)} · ${aliases[me.roleId]}</div><h2>${esc(me.name)}</h2><div class="skill-name">${esc(E.roles[me.roleId].skillName)}</div><button class="text-btn" id="my-info" style="padding:8px 0;color:#876239;font-size:10px;min-height:30px">角色说明 ↗</button></div></div>${stats(me)}<div class="my-goal"><div class="goal-row"><span>${goals[me.roleId]}</span><b>${me.achieved} / ${me.goal}</b></div>${progress(me)}</div></article>
  <section class="action-area" aria-label="当前行动">${mine?`<p class="action-title">${esc(phasePrompt(s))}</p><div class="actions">${s.actions.filter(a=>a.enabled).map((a,i,arr)=>`<button class="${i===0?'primary':'secondary'} ${arr.length===1?'single':''}" data-action="${s.actions.indexOf(a)}">${(a.payload.targetId||a.payload.partnerId)?art(a.payload.targetId||a.payload.partnerId,'action-avatar'):''}${actionLabel(a,s.owner)}${a.action==='request_draw'?`<span class="action-sub">${esc(costs(E.roles[viewer]))}</span>`:a.action==='use_skill'?`<span class="action-sub">${esc(E.roles[viewer].skillName)}</span>`:''}</button>`).join('')}</div>`:`<div class="waiting-panel">${person(s.owner)==='BOT'?'Bot 正在思考…':'等待 '+person(s.owner)+' 的选择'}<br>需要你回应时，会自动停下来</div>`}</section>
  <div class="activity" aria-live="polite">${esc(feed)}</div><footer class="bottom-row"><button id="journal">☷ 对局记录</button><button class="pace" id="pace">Bot ${speed}×</button><button id="rules">? 玩法</button></footer>`;
  document.getElementById('menu').onclick=menu;
  document.getElementById('rules').onclick=help;
  document.getElementById('my-info').onclick=()=>playerSheet(me.roleId);
  document.querySelectorAll('[data-player]').forEach(b=>b.onclick=()=>playerSheet(b.dataset.player));
  document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>{const a=s.actions[Number(b.dataset.action)];take(a,true);});
  document.getElementById('pace').onclick=()=>{speed=speed===1?2:1;renderGame();};
  document.getElementById('journal').onclick=()=>showSheet(`<span class="eyebrow">TABLE JOURNAL</span><h2>这一局的故事</h2><p>${esc(feed)}</p><details open><summary>原始结算记录</summary><div class="logs">${esc(text(s.logs.join('\n')))}</div></details>`);
  if(event)document.getElementById('event-info').onclick=()=>showSheet(`<span class="eyebrow">EVENT ${n} / 20</span><h2>${eventNames[n-1]}</h2><p>${globals[n-1]}</p><h3>${esc(s.lastEventInfo?.actorName)} 的角色效果</h3><p>${esc(window.KingsdayCardCopy?.[n-1]?.[ids.indexOf(turn.roleId)] || (turn.roleId==='role_volunteer' && n===4 ? '获得 1 件橙色物品。' : '无额外角色效果。'))}</p><details><summary>原卡英文说明</summary><p>${esc(s.lastEventInfo?.title)}\n${esc(s.lastEventInfo?.globalDesc)}\n${esc(s.lastEventInfo?.selfDesc)}</p></details>`);
  persist();schedule();
}
function pass(id) {
  stop();currentScreen='pass';
  app.innerHTML=`<section class="pass-screen">${crown}<div class="eyebrow">PASS THE PHONE</div><h1>请把手机交给${person(id)}</h1><p>轮到你的选择了。<br>准备好后，查看你的角色。</p><button class="primary" id="take-phone">我是${person(id)}，继续</button></section>`;
  document.getElementById('take-phone').onclick=()=>{viewer=id;currentScreen='game';renderGame();};
}
function schedule() {
  stop();if(currentScreen!=='game'||sheet.open||document.hidden)return;
  const s=E.snapshot();if(!s||s.gameOver||people.includes(s.owner))return;
  timer=setTimeout(()=>{timer=null;const now=E.snapshot();if(currentScreen!=='game'||sheet.open||people.includes(now.owner))return;const a=E.bot();if(!a){notify('这一步没有可执行选项，请查看对局记录。');return;}take(a,false);},1400/speed);
}
function take(a,human) {
  const before=E.snapshot();if(!before||before.gameOver||human!==people.includes(before.owner))return;
  stop();
  try {
    const after=E.act(a.action,a.payload);const owner=name(before.owner);lastAction=actionLabel(a,before.owner).replace(/<[^>]*>/g,'');
    const changes=[];for(const p of after.players){const old=before.players.find(o=>o.roleId===p.roleId);for(const k of Object.keys(resourceIcons)){const d=(p.status[k]||0)-(old.status[k]||0);if(d)changes.push(`${p.roleId===viewer?'你':p.name} ${resourceIcons[k]}${d>0?'+':''}${d}`);}}
    feed=changes.length?changes.slice(0,4).join(' · '):`${owner} · ${lastAction}`;
    if(a.action==='request_draw'&&after.ui.mode==='TURN_CHOICE'&&before.ui.mode==='TURN_CHOICE')notify('资源不足，无法支付抽卡代价。可以尝试角色技能。');
    persist();renderGame();
  } catch(e){notify('这一步未能执行，对局已保留。');console.error(e);}
}
function menu() {
  showSheet('<span class="eyebrow">TAKE A BREATH</span><h2>奇遇暂停中</h2><p>当前对局已自动保存。关闭菜单继续。</p><button class="secondary wide" id="back-lobby">保存并返回大厅</button>');
  document.getElementById('back-lobby').onclick=()=>{persist();currentScreen='lobby';sheet.close();lobby();};
}
function result(s) {
  stop();currentScreen='result';persist();const win=s.winners.some(id=>people.includes(id));const winner=s.players.find(p=>s.winners.includes(p.roleId));
  app.innerHTML=`<section class="result"><div class="eyebrow">THE END OF A LOVELY DAY</div><div class="medal">${winner?'♛':'✦'}</div><h1>${winner?(win?'这场奇遇，你赢了':'一场精彩的相遇'):'国王节，落幕了'}</h1><p class="muted small">${winner?`${s.winners.map(name).join('、')} 达成了胜利目标`:'事件卡已抽完，本局无人达成胜利条件'}</p>${winner?`<div class="podium">${art(winner.roleId)}</div>`:''}<div>${s.players.map(p=>`<div class="rank-row">${art(p.roleId)}<span>${esc(p.name)} <span class="badge">${person(p.roleId)}</span></span><b>${p.achieved} / ${p.goal}</b></div>`).join('')}</div><button class="primary wide" id="again">再来一场奇遇</button><button class="text-btn" id="home">回到大厅</button></section>`;
  document.getElementById('again').onclick=startDraw;document.getElementById('home').onclick=lobby;
}
document.addEventListener('visibilitychange',()=>{if(document.hidden){stop();if(E.snapshot())persist();}else schedule();});
lobby();
