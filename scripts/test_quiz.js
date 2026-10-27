/**
 * 刷题网页无浏览器自测：Node + vm 沙箱 + DOM stub
 * 运行：node test_quiz.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const HTML = path.join(__dirname, '..', 'web', '24套选择题刷题系统.html');
const html = fs.readFileSync(HTML, 'utf8');

const dm = html.match(/<script id="quiz-data" type="application\/json">([\s\S]*?)<\/script>/);
const sm = html.match(/<script>([\s\S]*?)<\/script>/);
if (!dm) { console.error('未找到数据块 quiz-data'); process.exit(1); }
if (!sm) { console.error('未找到逻辑脚本'); process.exit(1); }
const dataJson = dm[1];
const script = sm[1];

let pass = 0; const failures = [];
function ok(cond, msg) { if (cond) { pass++; } else { failures.push(msg); } }

/* ---------------- DOM stub ---------------- */
const store = {}, els = {}, downloads = [];
const calls = { fillText: 0 };
const fakeCtx = {
  fillStyle: '', strokeStyle: '', lineWidth: 0, font: '', textAlign: '',
  fillRect() {}, strokeRect() {}, clearRect() {}, beginPath() {}, arc() {},
  fill() {}, stroke() {}, moveTo() {}, lineTo() {}, fillText() { calls.fillText++; }
};

function mkEl(id) {
  const el = {
    id, value: '', _html: '', textContent: '', disabled: false, checked: true,
    className: '', _handlers: {}, parentNode: null, children: [], download: '',
    style: { setProperty(k, v) { this[k] = v; }, getPropertyValue(k) { return this[k]; } },
    appendChild(c) { this.children.push(c); if (c) c.parentNode = this; return c; },
    removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); },
    scrollIntoView() {}, select() {},
    click() { downloads.push(this.download); },
    setAttribute(k, v) { this['_a_' + k] = v; },
    getAttribute(k) {
      if (k in this) return this[k];
      return (this['_a_' + k] !== undefined) ? this['_a_' + k] : null;
    },
    getBoundingClientRect: () => ({ top: 120, left: 100, width: 300, height: 180, bottom: 300, right: 400 }),
    addEventListener(t, fn) { (this._handlers[t] = this._handlers[t] || []).push(fn); },
    dispatch(t, ev) { (this._handlers[t] || []).forEach(fn => fn(ev || {})); },
    getContext() { return fakeCtx; },
    toDataURL() { return 'data:image/png;base64,AAAA'; },
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      toggle(c, on) { if (on === undefined) on = !this._s.has(c); on ? this._s.add(c) : this._s.delete(c); return on; },
      contains(c) { return this._s.has(c); }
    }
  };
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._html; },
    set(v) { el._html = String(v); el.children.length = 0; }
  });
  return el;
}

const ctx = {
  console, innerWidth: 1200, innerHeight: 800,
  document: {
    readyState: 'complete',
    getElementById: id => {
      if (id === 'quiz-data') return { textContent: dataJson };
      return (els[id] = els[id] || mkEl(id));
    },
    querySelector: s => (els[s] = els[s] || mkEl(s)),
    createElement: t => (t === 'a' ? mkEl('a') : mkEl(t)),
    body: mkEl('body'),
    addEventListener(t, fn) { (this._h = this._h || {})[t] = (this._h[t] || []).concat(fn); }
  },
  navigator: {},
  localStorage: {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; }
  },
  requestAnimationFrame: fn => fn(),
  setTimeout: fn => { if (typeof fn === 'function') fn(); return 0; },
  Blob: function () {},
  URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} }
};
ctx.window = ctx;
ctx.addEventListener = function (t, fn) { (this._h = this._h || {})[t] = (this._h[t] || []).concat(fn); };
ctx.scrollTo = function () {};
ctx.print = function () { calls.printed = (calls.printed || 0) + 1; };

vm.createContext(ctx);
vm.runInContext(script, ctx);

/* ---------------- 启动 ---------------- */
ok(typeof ctx.onload === 'function', '脚本挂载了 window.onload');
ctx.onload();
const Q = ctx.window.__quiz;
const G = id => ctx.document.getElementById(id);
const HTML_APP = () => G('app').innerHTML;

ok(!!Q, '__quiz 已暴露');
ok(Q.SETS.length === 24, '共有 24 套题（实际 ' + Q.SETS.length + '）');
ok(Q.state.view === 'home', '初始视图为首页');

/* ---------------- 首页 ---------------- */
const home = HTML_APP();
ok((home.match(/setcard/g) || []).length === 24, '首页渲染 24 张套卡');
ok(home.indexOf('第 1 套') >= 0, '首页含「第 1 套」');
ok(home.indexOf('未开始') >= 0, '未开始状态可见');
ok(Q.SETS.every(s => s.items.length === 20), '每套均为 20 题');
ok(Q.SETS.every(s => s.items.every(q => q.answer && 'ABCD'.indexOf(q.answer) >= 0)), '每题都有答案');
ok(Q.SETS.every(s => s.items.every(q => q.options.A && q.options.B && q.options.C && q.options.D)), '每题四个选项齐全');

/* ---------------- 页面排版切换（默认单列，可切两栏） ---------------- */
const htmlBeforeLayout = HTML_APP();
ok(Q.layout() === 'single', '默认排版为「单列」（实际 ' + Q.layout() + '）');
ok(ctx.document.body.classList.contains('lay-single'), '默认 body 上已挂 lay-single');
ok(Q.setLayout('split') === true, '切到「两栏」返回 true');
ok(Q.layout() === 'split', '状态已切换为 split');
ok(!ctx.document.body.classList.contains('lay-single'), '切到两栏后 lay-single 被移除');
ok(store['quiz_layout_v1'] === 'split', '排版偏好已写入 localStorage（实际 ' + store['quiz_layout_v1'] + '）');
ok(Q.setLayout('split') === false, '重复选同一模式不做多余动作（返回 false）');
ok(Q.setLayout('bogus') === false, '非法模式被拒绝');
ok(Q.layout() === 'split', '非法值不会污染当前模式');
ok(Q.setLayout('single') === true && ctx.document.body.classList.contains('lay-single'),
  '切回「单列」后 lay-single 回来');
ok(store['quiz_layout_v1'] === 'single', '切回后偏好同步更新');
ok(HTML_APP() === htmlBeforeLayout, '切换排版不触发重渲染（app 区 HTML 逐字节未变）');
store['quiz_layout_v1'] = 'weird';
ok(Q.loadLayout() === 'single', 'localStorage 存了脏值 → 回落到默认单列');
store['quiz_layout_v1'] = 'split';
ok(Q.loadLayout() === 'split', '合法值能正常读回');
delete store['quiz_layout_v1'];

/* ---------------- 首次打开：动画分步引导 ---------------- */
ok(Q.onboardTotal() === 7, '引导共 7 步（实际 ' + Q.onboardTotal() + '）');
ok(Q.onboardOn() === true, '首次打开自动播放动画引导');
ok(Q.onboardStep() === 0, '引导从第 1 步开始');
ok(Q.onboardDone() === false, '只是播放还不算「看过」（未写标记）');
ok(store['quiz_onboard_v1'] === undefined, '播放过程中不写标记');
ok(Q.layoutTipOn() === false, '动画引导播放期间不叠排版气泡（避免两层提示）');
ok(HTML_APP().indexOf('data-act="onboard"') >= 0, '首页常驻「玩法引导」入口，可随时重看');
ok(html.indexOf('id="onboard"') > 0, '产物含引导层');
ok(html.indexOf('ob-mask') > 0 && html.indexOf('@keyframes obIn') > 0, '引导层带遮罩与入场动画');
ok(html.indexOf('@keyframes obPop') > 0 && html.indexOf('@keyframes obGlow') > 0, '引导内有元素弹出与光圈动画');
ok(html.indexOf('.onboard') > 0 && html.indexOf('ob-hi') > 0, '讲排版那一步会把顶栏抬到遮罩之上');

const obSeen = [];
for (let i = 0; i < 6; i++) { Q.onboardNext(); obSeen.push(Q.onboardStep()); }
ok(JSON.stringify(obSeen) === JSON.stringify([1, 2, 3, 4, 5, 6]), '「下一步」逐步推进到第 7 步（实际 ' + obSeen.join(',') + '）');
ok(Q.onboardOn() === true && Q.onboardStep() === 6, '最后一步仍在引导内');
ok(Q.obArt('modes').indexOf('闯关模式') >= 0 && Q.obArt('modes').indexOf('直刷模式') >= 0,
  '第 2 步用两张卡对比两种按套练法');
ok(Q.obArt('levels').indexOf('ob-lv') >= 0, '第 3 步用关卡轨道演示闯关流程');
ok(Q.obArt('drill').indexOf('ob-dots20') >= 0, '第 4 步用 20 个点演示直刷进度');
ok(Q.obArt('chapter').indexOf('ob-ch') >= 0 && Q.obArt('chapter').indexOf('第 12 套 · 第 7 题') >= 0,
  '第 5 步用章节条 + 来源角标演示知识点刷题');
ok(Q.obArt('tips').indexOf('单列 / 两栏') >= 0, '第 6 步讲界面操作（排版 / 续做 / 快捷键）');

Q.onboardNext();   // 最后一步 → 开始刷题
ok(Q.onboardOn() === false, '最后一步点「开始刷题」关闭引导');
ok(Q.onboardDone() === true && store['quiz_onboard_v1'] === '1', '关闭后写入「已看过」标记');
ok(Q.layoutTipOn() === false, '引导收尾时把排版气泡一并收掉（避免两层提示）');
ok(ctx.document.body.classList.contains('ob-hi') === false, '关闭后顶栏高亮已撤销');

Q.maybeShowOnboard();
ok(Q.onboardOn() === false, '看过之后不再自动播放');

Q.showOnboard();
ok(Q.onboardOn() === true && Q.onboardStep() === 0, '点「玩法引导」可以重看，从第 1 步起');
Q.onboardPrev();
ok(Q.onboardStep() === 0, '第 1 步时「上一步」不越界');
Q.onboardNext();
Q.onboardPrev();
ok(Q.onboardStep() === 0, '「上一步」能退回');
Q.closeOnboard();
ok(Q.onboardOn() === false, '「跳过」直接关闭');

/* ---------------- 排版气泡（首次打开让位给动画引导） ---------------- */
ok(typeof Q.maybeShowLayoutTip === 'function' && typeof Q.closeLayoutTip === 'function',
  '引导相关 API 已暴露');
ok(Q.layoutTipDone() === true, '动画引导关闭时顺带把排版说明标记为看过');
delete store['quiz_layout_tip_v1'];
delete store['quiz_layout_v1'];
Q.maybeShowLayoutTip();
ok(Q.layoutTipOn() === true, '没有动画引导挡着时，排版气泡照常弹');
ok(store['quiz_layout_tip_v1'] === undefined, '仅仅是「显示」还不算看过（未写标记）');
Q.closeLayoutTip();
ok(Q.layoutTipOn() === false, '关掉「就用单列」后引导收起');
ok(Q.layoutTipDone() === true && store['quiz_layout_tip_v1'] === '1', '关闭后标记「已看过」');
Q.maybeShowLayoutTip();
ok(Q.layoutTipOn() === false, '看过之后不再出现');
delete store['quiz_layout_tip_v1'];
store['quiz_layout_v1'] = 'split';
Q.maybeShowLayoutTip();
ok(Q.layoutTipOn() === false, '自己主动选过排版的老用户不会再被引导打扰');
delete store['quiz_layout_v1'];
ctx.innerWidth = 900;
delete store['quiz_layout_tip_v1'];
Q.maybeShowLayoutTip();
ok(Q.layoutTipOn() === false, '窄屏（≤1080px，开关本身隐藏）不弹引导');
ctx.innerWidth = 1200;
Q.setLayout('single');
Q.handleAct({ getAttribute: k => (k === 'data-act' ? 'tip-split' : null) });
ok(Q.layout() === 'split', '点「切换成两栏」会真的切成两栏');
ok(Q.layoutTipOn() === false, '点过引导按钮后气泡收起');
Q.setLayout('single');   // 复位，后续断言按单列走

/* 产物里的静态结构与 CSS 规则 */
ok(html.indexOf('class="layseg"') > 0, '顶栏存在排版切换控件');
ok(html.indexOf('data-act="layout" data-mode="single"') > 0
  && html.indexOf('data-act="layout" data-mode="split"') > 0, '切换控件含「单列」「两栏」两个按钮');
ok(html.indexOf('data-act="layout" data-mode="single" class="on"') > 0, '「单列」按钮默认就是选中态');
ok(html.indexOf('id="layoutTip"') > 0, '产物含排版引导气泡');
ok(html.indexOf('data-act="tip-split"') > 0 && html.indexOf('data-act="tip-close"') > 0,
  '引导气泡含「切换成两栏」「就用单列」两个按钮');
ok(html.indexOf('quiz_layout_tip_v1') > 0, '引导「已看过」的存储键在产物脚本里');
ok(/body\.lay-single \.split\{grid-template-columns:minmax\(0,1fr\);gap:0;\}/.test(html),
  '单列模式把网格收成一列的规则已进产物');
ok(html.indexOf('body.lay-single .split>.col-b{position:static;}') > 0,
  '单列模式下配图不再 sticky 的规则已进产物');
ok(html.indexOf('body.lay-single .wrap') > 0, '单列模式容器收回 1000px 的规则已进产物');
ok(/@media \(max-width:1080px\)\{ \.layseg\{display:none !important;\} \}/.test(html),
  '窄屏隐藏排版开关（窄屏本来就只能单列）');
ok(/@media print\{[\s\S]{0,900}?\.split\{grid-template-columns:minmax\(0,1fr\) !important/.test(html),
  '打印仍强制单列（不受开关影响）');

/* ---------------- 打开第 1 套：关卡开场卡 ---------------- */
Q.openSet(0);
ok(Q.state.view === 'quiz' && Q.state.stage === 'study', '进入学习页');
ok(Q.state.shell === 'intro', '进套后先停在关卡开场卡');
let h = HTML_APP();
ok(h.indexOf('LEVEL 1') >= 0, '开场卡显示 LEVEL 1');
ok(h.indexOf('第 1 关') >= 0, '开场卡显示「第 1 关」');
ok(h.indexOf('开始挑战') >= 0, '有「开始挑战」按钮');
ok(h.indexOf('个闯关 + 错题订正关 + 整套重刷关') >= 0, '开场卡说明关卡构成（题量自适应）');
ok((h.match(/class="lvnode/g) || []).length === 6, '轨道渲染 6 个关卡节点（实际 ' + (h.match(/class="lvnode/g) || []).length + '）');
ok((h.match(/locked/g) || []).length === 5, '首关时后面 5 关都是未解锁（实际 ' + (h.match(/locked/g) || []).length + '）');

Q.beginLevel();
ok(Q.state.shell === 'play' && Q.state.mode === 'preview', '开始挑战后进入预览模式');
ok(JSON.stringify(Q.state.list) === JSON.stringify([0, 1, 2, 3, 4]), '第 1 组为 5 题');
h = HTML_APP();
ok((h.match(/pvitem/g) || []).length === 5, '预览区铺开 5 题（实际 ' + (h.match(/pvitem/g) || []).length + '）');
ok(h.indexOf('开始答题') >= 0, '有「开始答题」按钮');
ok(h.indexOf('hl-ans') >= 0 || h.indexOf('hl-opt') >= 0, '预览中解析带高亮标记');
ok((h.match(/class="lvnode/g) || []).length === 6, '答题页顶部同样有关卡轨道');

/* ---------------- 开始答题 + 即时判定 ---------------- */
Q.startAnswer();
ok(Q.state.mode === 'answer', '切换到作答模式');
h = HTML_APP();
ok(h.indexOf('请选择一个选项') >= 0, '未作答时提示选择');
ok((h.match(/data-act="pick"/g) || []).length === 4, '渲染 4 个选项按钮');

const ITEMS = Q.SETS[0].items;
Q.pick('A');
ok(Q.state.results[0] === 'A', '第 1 题记录了选项 A');
h = HTML_APP();
ok(h.indexOf('正确答案') >= 0, '作答后立即展开正确答案');
ok(h.indexOf('解析') >= 0 || h.indexOf('hl-ans') >= 0, '作答后展开解析');

Q.pick('B');
ok(Q.state.results[0] === 'A', '已答题目再次点击不改变答案（一题只判一次）');

// 答对展示 + 连对计数
if (ITEMS[0].answer === 'A') {
  ok(HTML_APP().indexOf('答对') >= 0, '答对时显示答对状态');
  ok(Q.state.bestStreak === 1, '答对后连对计数为 1');
} else {
  ok(HTML_APP().indexOf('答错') >= 0, '答错时显示答错状态');
  ok(Q.state.streak === 0, '答错后连对归零');
}

/* ---------------- 上一题 / 下一题 ---------------- */
Q.next();
ok(Q.state.cur === 1, '下一题推进到第 2 题');
Q.prev();
ok(Q.state.cur === 0, '上一题退回第 1 题');
Q.prev();
ok(Q.state.cur === 0, '第 1 题时上一题不越界');

/* ---------------- 卡片提示：未答不能前进 ---------------- */
Q.next();                 // cur=1
const cur1 = Q.state.cur;
Q.next();
ok(Q.state.cur === cur1, '未作答时「下一题」不推进');

/* ---------------- 快捷键 ---------------- */
ctx.document._h.keydown.forEach(fn => fn({ key: '1' }));
ok(Q.state.results[1] === 'A', '键盘 1 选中 A');
ctx.document._h.keydown.forEach(fn => fn({ key: 'ArrowLeft' }));
ok(Q.state.cur === 0, '键盘 ← 上一题');
ctx.document._h.keydown.forEach(fn => fn({ key: 'ArrowRight' }));
ok(Q.state.cur === 1, '键盘 → 下一题');

/* ---------------- 完整走完第 1 套（首轮故意错 2 题） ---------------- */
Q.state.results = {};
Q.openSet(0);
let wrongPlan = { 0: true, 7: true };   // 第 1、8 题答错
for (let g = 0; g < 4; g++) {
  if (Q.state.shell === 'intro') Q.beginLevel();
  Q.startAnswer();
  for (let i = 0; i < 5; i++) {
    const itemIdx = Q.state.list[Q.state.cur];
    const right = ITEMS[itemIdx].answer;
    const key = wrongPlan[itemIdx] ? ['A', 'B', 'C', 'D'].find(k => k !== right) : right;
    Q.pick(key);
    Q.next();
  }
  // 每组答完弹本关结算卡，再进下一关
  ok(Q.state.shell === 'result', '第 ' + (g + 1) + ' 关答完出现结算卡');
  Q.nextLevel();
}
ok(Object.keys(Q.state.results).length === 20, '首轮 20 题全部作答（实际 ' + Object.keys(Q.state.results).length + '）');
ok(Q.state.shell === 'intro', '4 个小关走完进入「错题订正关」开场卡');
ok(Q.state.group === 4, '当前为第 5 关（错题订正关）（实际 ' + Q.state.group + '）');
ok(Q.levelKind(4) === 'retry' && Q.levelKind(5) === 'full', '第 5 关是订正关、第 6 关是整套重刷关');
ok(Q.unlockedLevel() === 4, '小关全部通关后解锁到错题订正关');

/* ---------------- 关卡结算卡与星数 ---------------- */
// 第 1、8 题答错 → 第 1 关 4/5（2 星）、第 2 关 4/5（2 星）、第 3、4 关满星（各 3 星）
ok(Q.starsTotal() === 10, '4 个小关星数汇总为 10（实际 ' + Q.starsTotal() + '）');
ok(Q.starsMax() === 18, '满星上限 = 6 关 × 3 星 = 18（实际 ' + Q.starsMax() + '）');
ok(Q.levelStars(5, 5) === 3 && Q.levelStars(4, 5) === 2 && Q.levelStars(3, 5) === 1 && Q.levelStars(2, 5) === 0,
  '星级规则：5/5=3星、4/5=2星、3/5=1星、2/5=0星');
ok(Q.levelStars(20, 20) === 3, '星级规则随题量自适应（20/20 = 3 星）');
ok(Q.levelCount() === 6 && Q.groupCount() === 4, '20 题 / 每组 5 题 → 4 个小关 + 订正关 + 通关考 = 6 关');
ok(Q.retryLevel() === 4 && Q.fullLevel() === 5, '订正关是第 5 关、整套重刷关是第 6 关');
ok(typeof Q.progress()['1'] === 'object' && Q.progress()['1'].levels, '每关过关即落盘（levels 已写入 localStorage）');
ok(Q.progress()['1'].levels['0'] && Q.progress()['1'].levels['0'].stars === 2, '第 1 关成绩已落盘（2 星）');

h = HTML_APP();
ok(h.indexOf('错 题 订 正') >= 0, '订正关开场卡显示「错题订正」');
ok(h.indexOf('首轮有 2 道错题') >= 0, '订正关开场卡说明错题数（实际：' + (h.match(/首轮有 \d+ 道错题/) || ['无'])[0] + '）');
ok(h.indexOf('本关题量') >= 0, '订正关开场卡显示本关题量');

Q.beginLevel();
ok(Q.state.stage === 'retry', '存在错题 → 进入错题重刷（实际 ' + Q.state.stage + '）');
ok(Q.state.list.length === 2, '错题池含 2 题（实际 ' + Q.state.list.length + '）');
ok(Q.state.retryTotal === 2, '错题总数记录为 2');

/* ---------------- 错题重刷：先看解析，答错留在队列 ---------------- */
ok(Q.state.revealRetry === true, '错题重刷先展示解析');
h = HTML_APP();
ok(h.indexOf('●') >= 0, '错题预览中选项字母被遮蔽为 ●');
ok(h.indexOf('正确答案') < 0, '错题预览不暴露正确答案标签');
ok(h.indexOf('思路解析') >= 0, '错题预览显示思路解析');
ok(h.indexOf('零基础详解') >= 0, '错题预览含零基础详解');
ok((h.match(/hl-masked/g) || []).length > 0, '遮蔽标记已生效');
// 配图上有中文标签（如「源程序」「控制器」），在遮蔽环节渲染等于直接把答案说出来
ok(h.indexOf('expimg') < 0, '错题重刷（答案遮蔽）不渲染配图，避免图上标签泄底');
ok(h.indexOf('我记住了') >= 0, '有「我记住了」按钮');

Q.pick('A');
ok(Object.keys(Q.state.retryResults).length === 0, '看解析阶段点击选项无效（需先点开始作答）');

Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'retry-go' : null) });
ok(Q.state.revealRetry === false, '点「我记住了」后进入作答');

let firstIdx = Q.state.list[Q.state.cur];
Q.pick(['A', 'B', 'C', 'D'].find(k => k !== ITEMS[firstIdx].answer));  // 故意答错
h = HTML_APP();
ok(h.indexOf('再看一遍解析') >= 0, '答错时提供「再看一遍解析」');
Q.handleAct({
  getAttribute: n => (n === 'data-act' ? 'retry-again' : null)
});
ok(Q.state.revealRetry === true, '答错后重看解析');
ok(Q.state.retryResults[firstIdx] === undefined, '重看解析时清空该题作答记录');

/* ---------------- 错题全部订正 → 订正关结算 → 整套重刷关 ---------------- */
let guard = 0;
while (Q.state.stage === 'retry' && Q.state.shell === 'play' && guard++ < 30) {
  if (Q.state.revealRetry) Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'retry-go' : null) });
  const idx = Q.state.list[Q.state.cur];
  Q.pick(ITEMS[idx].answer);
  Q.retryNext();
}
ok(guard < 30, '错题重刷可正常收敛（循环 ' + guard + ' 次）');
ok(Q.state.retryDone === 2, '已订正 2 题');
ok(Q.state.shell === 'result', '错题清空后弹订正关结算卡（实际 ' + Q.state.shell + '）');
h = HTML_APP();
ok(h.indexOf('错 题 已 清 零') >= 0, '订正关结算卡提示错题已清零');
ok(/1\/2<\/b><span>一次答对 50%/.test(h), '订正关结算卡展示「1/2 一次答对 50%」（其中 1 题是本段前面故意答错、重看解析后才答对的）');
ok(Q.state.levelStat[4].stars === 0, '订正关一次答对率 50% → 0 星（指标确实按「一次答对」算）');
ok(h.indexOf('进入整套重刷') >= 0, '订正关结算卡提供「进入整套重刷」');

Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'level-next' : null) });
ok(Q.state.group === 5 && Q.state.shell === 'intro', '订正关之后进入第 6 关开场卡');
ok(Q.levelKind(5) === 'full', '第 6 关是整套重刷关');
Q.beginLevel();
ok(Q.state.stage === 'full' && Q.state.shell === 'play', '开始挑战后进入整套重刷（实际 ' + Q.state.stage + '/' + Q.state.shell + '）');
ok(Q.state.list.length === 20, '整套重刷为完整 20 题');
h = HTML_APP();
ok(h.indexOf('整套重刷') >= 0, '整套重刷标签可见');
ok(h.indexOf('pvitem') < 0, '整套重刷不再预览解析');

/* ---------------- 整套重刷（本轮全对） ---------------- */
for (let i = 0; i < 20; i++) {
  const idx = Q.state.list[Q.state.cur];
  Q.pick(ITEMS[idx].answer);
  Q.next();
}
ok(Q.state.stage === 'done', '整套重刷结束 → 完成');
ok(Q.state.shell === 'result', '整套重刷关结束先弹结算卡（而不是直接跳完成页）');
h = HTML_APP();
ok(h.indexOf('全 套 完 成') >= 0, '整套重刷关结算卡显示「全套完成」');
ok(h.indexOf('整套重刷 通关') >= 0, '整套重刷关结算卡标题正确');
ok((h.match(/★/g) || []).length >= 3, '结算卡渲染星数');
ok(h.indexOf('查看通关成绩') >= 0, '最后一关的按钮是「查看通关成绩」');
// 4 小关 10 星 + 订正关 0 星 + 通关考 3 星 = 13
// 订正关那 1 题是本段前面「故意答错 → 退回重看解析」的题，不算一次答对，所以 1/2 → 0 星
ok(Q.starsTotal() === 13, '总星数 13/18（实际 ' + Q.starsTotal() + '）');

Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'level-next' : null) });
ok(Q.state.view === 'done', '点「查看通关成绩」进入完成页');

/* ---------------- 成绩与持久化 ---------------- */
const rec = Q.progress()['1'];
ok(!!rec && rec.done === true, '该套标记为已完成');
ok(rec.firstScore === 18, '首轮正确 18/20（实际 ' + rec.firstScore + '）');
ok(rec.fullScore === 20, '整套重刷正确 20/20（实际 ' + rec.fullScore + '）');
ok(store['quiz_progress_v2'] && store['quiz_progress_v2'].indexOf('"done":true') > -1, '进度已写入 localStorage');

/* ---------------- 完成页与证书 ---------------- */
h = HTML_APP();
ok(h.indexOf('首轮错题回顾') >= 0, '完成页含错题回顾');
ok(h.indexOf('certCanvas') >= 0, '完成页含证书画布');
ok(h.indexOf('简约专业') >= 0 && h.indexOf('红金喜庆') >= 0, '两种证书风格可切换');
ok(calls.fillText > 0, '证书已绘制文字（fillText 调用 ' + calls.fillText + ' 次）');

const before = calls.fillText;
Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'cert-style' : (n === 'data-style' ? 'gold' : null)) });
ok(Q.state.certStyle === 'gold', '可切换到红金风格');
ok(calls.fillText > before, '切换风格后重绘证书');

// 姓名输入
Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'name' : null) });
ctx.document._h.input.forEach(fn => fn({ target: { getAttribute: () => 'name', value: '张三' } }));
ok(Q.state.name === '张三', '姓名输入写入状态');

Q.drawCert();
Q.downloadPNG();
ok(downloads.length === 1, '导出了 1 个文件');
ok(/张三_第1套_通关证书\.png/.test(downloads[0]), '导出文件名为「张三_第1套_通关证书.png」（实际 ' + downloads[0] + '）');

Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'print' : null) });
ok(calls.printed === 1, '触发打印（另存为 PDF）');

/* ---------------- 安卓 App 适配（原生桥 AndroidSave） ---------------- */
ok(Q.inAndroidApp() === false, '没有原生桥时判定为普通浏览器环境');
ok(HTML_APP().indexOf('data-act="print"') >= 0, '浏览器环境保留「打印 / 另存为 PDF」入口');
ok(HTML_APP().indexOf('下载 PNG') >= 0, '浏览器环境按钮文案为「下载 PNG」');

const savedToAlbum = [];
ctx.AndroidSave = { png: (d, n) => { savedToAlbum.push([d, n]); } };
ok(Q.inAndroidApp() === true, '注入 AndroidSave 后判定为安卓 App 环境');
Q.render();                       // 按安卓环境重新渲染证书区
h = HTML_APP();
ok(h.indexOf('data-act="print"') < 0, '安卓环境隐藏打印入口（WebView 里打印没有意义）');
ok(h.indexOf('保存到相册') >= 0, '安卓环境按钮文案变为「保存到相册」');

const dlBefore = downloads.length;
Q.downloadPNG();
ok(savedToAlbum.length === 1, '导出走原生桥存相册（调用 ' + savedToAlbum.length + ' 次）');
ok(downloads.length === dlBefore, '安卓环境不再走 <a download>');
ok(savedToAlbum[0][0].indexOf('data:image/png;base64,') === 0, '交给原生的是 PNG data URL');
ok(/张三_第1套_通关证书\.png/.test(savedToAlbum[0][1]),
  '原生收到的文件名带姓名与套号（实际 ' + savedToAlbum[0][1] + '）');
delete ctx.AndroidSave;
Q.render();                       // 还原成浏览器环境

/* ---------------- 零基础详解与遮蔽逻辑 ---------------- */
ok(Q.SETS.every(s => s.items.every(q => q.easy && q.easy.length > 100)), '每题都带零基础详解');
ok(Q.SETS.every(s => s.items.every(q => q.easy.indexOf('**') < 0 && q.easy.indexOf('##') < 0)), '零基础详解不含 Markdown 符号');
ok(Q.easyHtml(Q.SETS[0].items[0]).indexOf('零基础详解') >= 0, '零基础详解块可渲染');
const mk = Q.maskHtml('<b class="hl-ans">故选B</b>，<b class="hl-opt">C</b>项，见 <b class="hl-term">CPU</b>');
ok(mk.indexOf('故选●') >= 0, 'maskHtml 遮蔽「故选B」中的字母');
ok(mk.indexOf('>C<') < 0, 'maskHtml 遮蔽独立选项字母');
ok(mk.indexOf('CPU') >= 0, 'maskHtml 保留英文术语 CPU');

/* ---------------- 逐项讲解分行 ---------------- */
const nLine = Q.SETS.reduce((n, s) => n + s.items.filter(q => q.analysis.indexOf('optline') >= 0).length, 0);
const eLine = Q.SETS.reduce((n, s) => n + s.items.filter(q => q.easy.indexOf('optline') >= 0).length, 0);
ok(nLine > 300, '普通解析中逐项讲解已分行（' + nLine + ' 题）');
ok(eLine > 300, '零基础详解中逐项讲解已分行（' + eLine + ' 题）');
const sample = Q.SETS[12].items[13].analysis;
ok((sample.match(/class="optline"/g) || []).length >= 3, '选项讲解各自独立成行（示例 ' + (sample.match(/class="optline"/g) || []).length + ' 行）');

/* ---------------- 并列选项之间的顿号 ---------------- */
const allText = Q.SETS.reduce((a, s) => a.concat(s.items.map(q => q.analysis + q.easy)), []);
const badSep = allText.filter(t => /<b class="hl-opt">[A-D]<\/b>\s*[，,]\s*<b class="hl-opt">/.test(t)).length;
const goodSep = allText.filter(t => /<b class="hl-opt">[A-D]<\/b>、<b class="hl-opt">/.test(t)).length;
ok(badSep === 0, '不存在用逗号分隔的并列选项（实际 ' + badSep + ' 处）');
ok(goodSep > 100, '并列选项已用顿号连接（' + goodSep + ' 处）');

/* ---------------- 返回首页后状态更新 ---------------- */
Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'home' : null) });
ok(Q.state.view === 'home', '返回首页');
h = HTML_APP();
ok(h.indexOf('is-done') >= 0, '首页显示已完成样式');
ok(h.indexOf('首轮 18/20') >= 0, '首页显示该套成绩');

/* ---------------- 清除记录 ---------------- */
Q.openSet(0);
Q.resetSet();
ok(!Q.progress()['1'], '清除本套记录后进度被移除');
ok(Q.state.view === 'quiz' && Q.state.shell === 'intro', '重置后回到该套开场卡');

/* ---------------- 关卡：解锁顺序 / 跳关 / 重刷 / 断点续做 ---------------- */
Q.resetSet();
ok(Q.unlockedLevel() === 0, '清空记录后只解锁第 1 关');
ok(Q.state.group === 0 && Q.state.shell === 'intro', '从头开始，停在开场卡');

// 未解锁的关卡点不动
Q.jumpToLevel(3);
ok(Q.state.group === 0, '未解锁的关卡点了也不跳转（必须按序）');

// 走完第 1 关 → 解锁第 2 关
Q.beginLevel();
Q.startAnswer();
for (let i = 0; i < 5; i++) { Q.pick(ITEMS[Q.state.list[Q.state.cur]].answer); Q.next(); }
ok(Q.state.shell === 'result' && Q.state.doneLv[0] === true, '第 1 关通关并弹结算卡');
ok(Q.unlockedLevel() === 1, '第 1 关通关后解锁到第 2 关');
h = HTML_APP();
ok(h.indexOf('第 1 关 · 识途 通关') >= 0, '结算卡显示关卡名「识途」');
ok(h.indexOf('进入第 2 关') >= 0, '结算卡提供「进入第 2 关」');

Q.nextLevel();
ok(Q.state.group === 1 && Q.state.shell === 'intro', '进入第 2 关开场卡');

// 断点续做：模拟关掉页面再打开
const savedLv = JSON.parse(store['quiz_progress_v2']);
ok(Object.keys(savedLv['1'].levels).length === 1, '只有第 1 关的成绩被落盘（每关过关即存）');
ok(savedLv['1'].results['0'] === ITEMS[0].answer, '作答记录一并落盘，续做时不会丢');
Q.openSet(0);
ok(Q.state.group === 1, '重新进套时从「已解锁的第 2 关」继续，而不是从第 1 关重来');
ok(Q.state.doneLv[0] === true && Q.state.stars[0] === 3, '第 1 关的成绩被正确恢复（3 星）');

// 首页套卡要反映关卡进度
Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'home' : null) });
h = HTML_APP();
ok(h.indexOf('已得 3/18 星') >= 0, '首页套卡显示已得星数（实际片段：' + (h.match(/已得 \d+\/\d+ 星/) || ['无'])[0] + '）');
ok(h.indexOf('继续第 2 关') >= 0, '首页套卡提示从第 2 关继续');
ok(h.indexOf('进行中') >= 0, '首页套卡状态为「进行中」');
Q.openSet(0);

// 重刷已通关的关卡
Q.jumpToLevel(0);
ok(Q.state.group === 0 && Q.state.shell === 'intro', '点轨道上已通关的第 1 关 → 进开场卡重刷');
ok(!Q.state.doneLv[0] && !Q.state.stars[0], '重刷时该关成绩被清空');
Q.beginLevel();
ok(!Q.state.results[0], '重刷该关时本关作答记录已清空（否则 pick 会拒绝作答）');
Q.pick(ITEMS[0].answer);
ok(Q.state.results[0] === ITEMS[0].answer, '重刷时可以重新作答');

/* ---------------- 关卡数随题量自适应 ---------------- */
ok(Q.levelCount() === Math.ceil(ITEMS.length / 5) + 2, '关卡数 = ceil(题数/每组) + 订正关 + 通关考');
ok(Q.SETS.every(s => {
  const gc = Math.ceil(s.items.length / 5);
  return gc >= 1;
}), '每套都能算出至少 1 个小关');

/* ---------------- 清除记录 ---------------- */
Q.resetSet();
ok(!Q.progress()['1'], '再次清除记录生效');
Q.beginLevel();   // 回到第 1 关预览，供后面的配图/两栏断言使用

/* ---------------- 首轮全对：订正关无需订正，自动满星 ---------------- */
Q.openSet(1);
const IT2 = Q.SETS[1].items;
for (let g = 0; g < 4; g++) {
  if (Q.state.shell === 'intro') Q.beginLevel();
  Q.startAnswer();
  for (let i = 0; i < 5; i++) { Q.pick(IT2[Q.state.list[Q.state.cur]].answer); Q.next(); }
  Q.nextLevel();
}
ok(Q.state.group === 4 && Q.state.shell === 'intro', '第 2 套全对后进入订正关开场卡');
h = HTML_APP();
ok(h.indexOf('首轮全部答对') >= 0, '首轮全对时开场卡提示无需订正');
ok(h.indexOf('直接过关') >= 0, '首轮全对时按钮变为「直接过关」');
Q.beginLevel();
ok(Q.state.shell === 'result' && Q.state.stars[4] === 3, '点「直接过关」立即满星通过订正关（实际 ' + Q.state.stars[4] + ' 星）');
ok(Q.state.doneLv[4] === true, '订正关记为已通关');
h = HTML_APP();
ok(h.indexOf('首轮全对，没有需要订正的题') >= 0, '订正关结算卡说明无错可订');
Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'level-next' : null) });
ok(Q.state.group === 5 && Q.levelKind(5) === 'full', '接着进入整套重刷关');

Q.openSet(0);
Q.beginLevel();   // 恢复：第 1 套第 1 关预览，供后面的配图断言使用

/* ---------------- 解析配图 ---------------- */
// 以 images/set_XX/ 里实际有没有图为准，别把「第几套有图」写死 ——
// 每补一套图都要改测试的话，测试会因为数据变了而假失败。
// 分三类：整套齐全 / 只配了一部分（缺某几题）/ 完全没配。
const IMG_ROOT = path.join(__dirname, '..', 'images');
const pad2 = n => (n < 10 ? '0' + n : '' + n);
const hasImg = (set, no) => fs.existsSync(path.join(IMG_ROOT, 'set_' + pad2(set), no + '.png'));
const setsWithImg = [], setsPartial = [], setsNoImg = [];
Q.SETS.forEach(s => {
  const n = s.items.filter(q => hasImg(s.set, q.no)).length;
  if (n === 0) setsNoImg.push(s);
  else if (n === s.items.length) setsWithImg.push(s);
  else setsPartial.push(s);
});
ok(setsWithImg.length >= 1, '至少有一套配图齐全（实际 ' + setsWithImg.length + ' 套）');
ok(setsWithImg.every(s => s.items.length === 20), '配图齐全的套均为 20 题');
ok(setsWithImg.every(s => s.items.every(q => (q.image || '').indexOf('data:image/png;base64,') === 0)),
  '配图齐全的套：每题都内嵌了图片');
ok(setsWithImg.every(s => s.items.every(q => q.image.indexOf('iVBORw0KGgo') > 0)),
  '内嵌数据是合法 PNG（文件头校验通过）');
const imgLens = setsWithImg.reduce((a, s) => a.concat(s.items.map(q => q.image.length)), []);
ok(Math.min.apply(null, imgLens) > 30000,
  '每张配图体积正常（最小 ' + Math.round(Math.min.apply(null, imgLens) * 3 / 4 / 1024) + ' KB）');

// 部分配图：有图的题嵌图、缺图的题 image 为空 —— 关键是「不能串位」
ok(setsPartial.every(s => s.items.every(q =>
  hasImg(s.set, q.no) === ((q.image || '').indexOf('data:image/png;base64,') === 0))),
  '部分配图的套：有图文件才有 image，缺图的那题留空（不串位）：'
  + setsPartial.map(s => '第' + s.set + '套缺'
      + s.items.filter(q => !hasImg(s.set, q.no)).map(q => '第' + q.no + '题').join('、')).join('；'));
ok(setsNoImg.every(s => s.items.every(q => !q.image)), '未配图的套：没有被误插空图片');

ok(Q.imgHtml(Q.SETS[0].items[0]).indexOf('expimg') >= 0, 'imgHtml 渲染出配图块');
ok(Q.imgHtml(Q.SETS[0].items[0]).indexOf('生活类比') >= 0, '配图块带说明文字');
ok(Q.imgHtml(Q.SETS[0].items[0]).indexOf('data:image/png;base64,') > 0, '配图块带图片数据');
ok(Q.imgHtml({ no: 1 }) === '' && Q.imgHtml(null) === '', '没有配图时 imgHtml 返回空串（不留空位）');

ok(HTML_APP().indexOf('expimg') >= 0, '已配图的套：预览区确实出现配图');
ok((HTML_APP().match(/expimg/g) || []).length === 5, '预览 5 题各插入 1 张配图');
if (setsNoImg.length) {
  Q.openSet(Q.SETS.indexOf(setsNoImg[0]));
  Q.beginLevel();
  ok(HTML_APP().indexOf('expimg') < 0, '未配图的套：解析区不出现配图块（不留空位）');
  Q.openSet(0);
}
if (setsPartial.length) {
  // 第 1 关（前 5 题）里恰好有图的题才渲染配图，缺图那题退化成单列
  const ps = setsPartial[0];
  const expect = [0, 1, 2, 3, 4].filter(i => hasImg(ps.set, ps.items[i].no)).length;
  Q.openSet(Q.SETS.indexOf(ps));
  Q.beginLevel();
  const html = HTML_APP();
  ok((html.match(/expimg/g) || []).length === expect,
    '部分配图的套：第 1 关 5 题里只渲染 ' + expect + ' 张配图（实际 '
    + (html.match(/expimg/g) || []).length + '）');
  ok((html.match(/class="split one"/g) || []).length === 5 - expect,
    '缺图的那 ' + (5 - expect) + ' 题退化成单列（不留空栏）');
  Q.openSet(0);
}

/* ---------------- 两栏布局（方案 B：左文字 / 右配图） ---------------- */
const q1 = Q.SETS[0].items[0];
const two = Q.splitHtml('<p>左侧</p>', Q.imgHtml(q1));
ok(two.indexOf('class="split"') >= 0, 'splitHtml：有图时生成两栏容器');
ok(two.indexOf('class="split one"') < 0, 'splitHtml：有图时不是单列');
ok(two.indexOf('col-a') >= 0 && two.indexOf('col-b') >= 0, 'splitHtml：左右两栏都在');
ok(two.indexOf('data-act="zoomimg"') >= 0, '配图带放大触发标记');
ok(two.indexOf('data-src="data:image/png') > 0, '配图带原图地址，供放大时使用');
const one = Q.splitHtml('<p>左侧</p>', '');
ok(one.indexOf('class="split one"') >= 0, 'splitHtml：无图时退化为单列（split one）');
ok(one.indexOf('col-b') < 0, 'splitHtml：无图时不输出空右栏');
ok(one.indexOf('expimg') < 0, 'splitHtml：无图时不输出配图块');

Q.openSet(0);
Q.beginLevel();
ok((HTML_APP().match(/class="split"/g) || []).length === 5, '预览页 5 题均为两栏');
ok((HTML_APP().match(/class="qbadge"/g) || []).length === 5, '题干带题号徽章（5 个）');
Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'start-answer' : null) });
ok(HTML_APP().indexOf('class="split one"') >= 0, '作答中（未揭晓）为单列，不预留空的图片栏');
Q.pick(Q.SETS[0].items[0].answer);
ok((HTML_APP().match(/class="split"/g) || []).length === 1, '作答后揭晓解析时为两栏');

/* ---------------- 配图放大 ---------------- */
ok(Q.imgBoxOpen() === false, '放大层初始为关闭');
Q.openImgBox('data:image/png;base64,AAAA');
ok(Q.imgBoxOpen() === true, 'openImgBox 能打开放大层');
Q.closeImgBox();
ok(Q.imgBoxOpen() === false, 'closeImgBox 能关闭放大层');
Q.closeImgBox();
ok(Q.imgBoxOpen() === false, '重复关闭不报错（幂等）');

/* ---------------- 直刷模式（不分组，直接连做 20 题） ---------------- */
Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'home' : null) });
h = HTML_APP();
ok((h.match(/data-act="drill"/g) || []).length === 24,
  '首页 24 张套卡各带 1 个直刷入口（实际 ' + (h.match(/data-act="drill"/g) || []).length + '）');
ok(h.indexOf('直刷 20 题') >= 0, '套卡上有「直刷 20 题」按钮');
ok(!G('authorBadge').classList.contains('hidden'), '首页显示署名徽标');

Q.openDrill(2);
ok(Q.state.view === 'drill' && Q.state.stage === 'drill', '进入直刷模式（实际 ' + Q.state.view + '/' + Q.state.stage + '）');
ok(G('authorBadge').classList.contains('hidden'), '直刷界面隐藏署名徽标');
ok(Q.state.list.length === 20 && Q.state.cur === 0, '直刷按 1→20 顺序铺满整套（实际 ' + Q.state.list.length + ' 题）');
h = HTML_APP();
ok(h.indexOf('直刷模式') >= 0, '直刷页显示模式标签');
ok(h.indexOf('lvnode') < 0, '直刷页不出现关卡轨道');
ok(h.indexOf('pvitem') < 0, '直刷页不预先铺解析（无预览环节）');
ok((h.match(/class="opt"/g) || []).length === 4, '直刷页直接呈现 4 个选项');
ok(h.indexOf('请选择一个选项') >= 0, '未作答时提示先选答案');

Q.next();
ok(Q.state.cur === 0, '未作答时「下一题」不推进');

const DITEMS = Q.SETS[2].items;
Q.pick(DITEMS[0].answer);
h = HTML_APP();
ok(Q.state.drillResults[0] === DITEMS[0].answer, '直刷记录作答（第 1 题）');
ok(h.indexOf('正确答案') >= 0, '答完立刻展开正确答案');
ok(h.indexOf('零基础详解') >= 0, '答完立刻给出解析内容');

Q.next();
ok(Q.state.cur === 1, '直刷可以进入下一题');
Q.prev();
ok(Q.state.cur === 0, '直刷可以回看上一题');
Q.pick(DITEMS[0].answer === 'A' ? 'B' : 'A');
ok(Q.state.drillResults[0] === DITEMS[0].answer, '已答题再点不会改答案');

// 20 题走完：第 2 题故意答错，其余全对
Q.next();
let g2 = 0;
while (Q.state.view === 'drill' && g2++ < 40) {
  const idx = Q.state.list[Q.state.cur];
  if (!Q.state.drillResults[idx]) {
    Q.pick(idx === 1 ? ['A', 'B', 'C', 'D'].find(k => k !== DITEMS[1].answer) : DITEMS[idx].answer);
  }
  Q.next();
}
ok(g2 < 40, '直刷 20 题可正常收敛（循环 ' + g2 + ' 次）');
ok(Q.state.view === 'drill-done', '20 题答完自动交卷（实际 ' + Q.state.view + '）');
ok(Q.drillRight() === 19, '直刷统计答对 19/20（实际 ' + Q.drillRight() + '）');
h = HTML_APP();
ok(h.indexOf('直刷完成') >= 0, '直刷成绩页标题正确');
ok(h.indexOf('19/20') >= 0, '成绩页给出答对数');
ok(h.indexOf('错题回顾') >= 0, '成绩页含错题回顾');
ok(h.indexOf('第 2 题') >= 0, '错题回顾定位到具体题号');
ok(h.indexOf('certCanvas') < 0, '直刷不发证书（证书属于闯关通关）');
ok(G('authorBadge').classList.contains('hidden'), '直刷成绩页同样不显示署名徽标');

const drec = Q.progress()['3'];
ok(!!drec && !!drec.drill && drec.drill.right === 19, '直刷成绩已写入 localStorage');
ok(!!drec.drillBest && drec.drillBest.total === 20, '同时记录直刷最好成绩');
ok(!drec.levels, '直刷不改动闯关关卡成绩（两套记录互不干扰）');

Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'home' : null) });
h = HTML_APP();
ok(h.indexOf('直刷 19/20') >= 0, '首页套卡回显直刷成绩（实际片段：' + (h.match(/直刷 \d+\/\d+/) || ['无'])[0] + '）');
ok(!G('authorBadge').classList.contains('hidden'), '回到首页徽标重新出现');

/* ---------------- 知识点章节刷题 ---------------- */
Q.closeOnboard();
Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'home' : null) });
h = HTML_APP();

ok(Array.isArray(Q.CH) && Q.CH.length === 13, '知识点共 13 章（实际 ' + (Q.CH ? Q.CH.length : '无') + '）');
ok(Q.CH.every(c => c.total > 0), '每章都有题目，不存在空章');
ok(Q.CH.every(c => c.objs.length === c.total), '每章挂载题目数与 total 一致');
ok(Q.CH.reduce((a, c) => a + c.total, 0) === 480, '章节题目合计 480 题（实际 ' + Q.CH.reduce((a, c) => a + c.total, 0) + '）');
ok(Q.CH.every(c => c.sets >= 1 && c.sets <= 24), '每章覆盖套数落在 1–24 之间');
ok(Q.CH.every(c => c.objs.every((q, i) => i === 0 ||
  (q.set * 100 + q.no) > (c.objs[i - 1].set * 100 + c.objs[i - 1].no))),
  '每章题目按「第几套 → 第几题」升序排列');
ok(Q.CH.every(c => c.objs.every(q => Q.SETS[q.set - 1].items[q.no - 1] === q)),
  '章节里引用的是同一道题对象（没有复制、没有串位）');
ok(Q.CH.every(c => c.objs.every(q => q.set >= 1 && q.set <= 24 && q.no >= 1 && q.no <= 20)),
  '每题都带着合法的套号与题号');

const chKeys = Q.CH.reduce((a, c) => a.concat(c.objs.map(q => q.set + '-' + q.no)), []);
ok(chKeys.length === 480, '题目不去重，480 条全在（实际 ' + chKeys.length + '）');
ok(new Set(chKeys).size === 480, '同一道题在同一章里不会被挂两次');
const chCover = {};
chKeys.forEach(k => { const s = k.split('-')[0]; chCover[s] = (chCover[s] || 0) + 1; });
ok(Object.keys(chCover).length === 24 && Object.keys(chCover).every(s => chCover[s] === 20),
  '24 套各 20 题全部归入章节（无遗漏）');
// 跨套重复的题必须保留成两条（不去重）
const dupStem = {};
Q.CH.forEach(c => c.objs.forEach(q => {
  const k = c.id + '||' + q.stem;
  dupStem[k] = (dupStem[k] || 0) + 1;
}));
ok(Object.keys(dupStem).some(k => dupStem[k] > 1), '同一章里同一道题出现在多套时都保留（未去重）');

ok(h.indexOf('data-act="chapters"') >= 0, '首页有「按知识点刷题」入口');
ok(h.indexOf('按知识点刷题 · 13 章 480 题') >= 0, '首页入口写明章节数与题量');

Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'chapters' : null) });
h = HTML_APP();
ok(Q.state.view === 'chapters', '进入章节列表（实际 ' + Q.state.view + '）');
ok((h.match(/class="chcard/g) || []).length === 13, '章节列表渲染 13 张章卡');
ok(h.indexOf('计算机发展与信息表示') >= 0, '章卡显示章名');
ok(h.indexOf('53 题') >= 0, '章卡显示题量');
ok(h.indexOf('覆盖 ') >= 0, '章卡显示覆盖套数');
ok(G('authorBadge').classList.contains('hidden'), '章节列表不显示署名徽标');
ok(G('topMeta').innerHTML.indexOf('知识点章节') >= 0, '顶栏标注「知识点章节」');

/* 章节刷题不动闯关 / 直刷进度：先取快照 */
const setSnap = JSON.stringify(Q.progress()['1'] || {});

Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'chapter' : (n === 'data-ch' ? '0' : null)) });
h = HTML_APP();
ok(Q.state.view === 'chapter' && Q.state.stage === 'chapter', '进入章节刷题');
ok(Q.state.chapterIdx === 0, '记录当前章下标');
ok(Q.state.list.length === Q.CH[0].total, '题目列表长度 = 本章题量');
ok(Object.keys(Q.state.chapterResults).length === 0, '进入时本章作答记录为空');
ok(h.indexOf('class="qsrc"') >= 0, '题卡左上角有来源角标');
const c0 = Q.CH[0].objs[0];
ok(h.indexOf('第 ' + c0.set + ' 套 · 第 ' + c0.no + ' 题') >= 0,
  '角标写明「第几套第几题」（应为第 ' + c0.set + ' 套 · 第 ' + c0.no + ' 题）');
ok(h.indexOf(Q.CH[0].name) >= 0, '页面标题是本章章名');
ok(h.indexOf('本章第 1/' + Q.CH[0].total + ' 题') >= 0, '显示本章进度');

Q.pick(c0.answer);
h = HTML_APP();
ok(Q.state.chapterResults[0] === c0.answer, '章节刷题记录作答');
ok(h.indexOf('正确答案') >= 0, '答完立刻出正确答案');
ok(h.indexOf('零基础详解') >= 0, '答完立刻给出解析');
ok(Q.chapterRight() === 1, '本章答对数统计正确');

Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'ch-next' : null) });
ok(Q.state.cur === 1, '「下一题」推进到第 2 题');
Q.chNext();
ok(Q.state.cur === 1, '第 2 题未作答时「下一题」不推进');
Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'ch-prev' : null) });
ok(Q.state.cur === 0, '「上一题」回到第 1 题');
ctx.document._h.keydown.forEach(fn => fn({ key: 'ArrowRight' }));
ok(Q.state.cur === 1, '快捷键 → 进入下一题');
ctx.document._h.keydown.forEach(fn => fn({ key: '1' }));
ok(!!Q.state.chapterResults[1], '快捷键 1 在章节里选中 A');

// 本章走完：第 2 题故意答错，其余全对
let g3 = 0;
while (Q.state.view === 'chapter' && g3++ < 200) {
  const idx = Q.state.list[Q.state.cur];
  if (!Q.state.chapterResults[idx]) {
    const right = Q.chItems()[idx].answer;
    Q.pick(idx === 1 ? ['A', 'B', 'C', 'D'].find(k => k !== right) : right);
  }
  Q.chNext();
}
ok(g3 < 200, '本章可正常走完（循环 ' + g3 + ' 次）');
ok(Q.state.view === 'chapter-done', '答完自动进入本章成绩页（实际 ' + Q.state.view + '）');
ok(Q.chapterRight() === Q.CH[0].total - 1, '答对数 = 总题数 - 1（实际 ' + Q.chapterRight() + '）');
h = HTML_APP();
ok(h.indexOf('本章刷完') >= 0, '成绩页标题正确');
ok(h.indexOf('错题回顾') >= 0, '成绩页含错题回顾');
const wrongIdx0 = Number(Object.keys(Q.state.chapterResults).find(i => Q.state.chapterResults[i] !== Q.chItems()[i].answer));
ok(wrongIdx0 >= 0, '本章确实记录了错题');
const wq = Q.chItems()[wrongIdx0];
ok(h.indexOf('第 ' + wq.set + ' 套 · 第 ' + wq.no + ' 题') >= 0,
  '错题回顾标出来源（应为第 ' + wq.set + ' 套 · 第 ' + wq.no + ' 题）');
ok(h.indexOf('certCanvas') < 0, '章节刷题不发证书');

const crec = (Q.progress().chapters || {})[1];
ok(!!crec && !!crec.last && crec.last.total === Q.CH[0].total, '本章成绩写入 progress.chapters');
ok(!!crec.best && crec.best.right === Q.CH[0].total - 1, '记录本章最佳成绩');
ok(JSON.stringify(Q.progress()['1'] || {}) === setSnap, '章节刷题不碰闯关 / 直刷进度');

Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'ch-again' : null) });
ok(Q.state.view === 'chapter' && Q.state.cur === 0, '「再刷本章」回到第 1 题');
ok(Object.keys(Q.state.chapterResults).length === 0, '「再刷本章」清空作答记录');

// 全对一遍：最佳应刷新为满分
let g4 = 0;
while (Q.state.view === 'chapter' && g4++ < 200) {
  const idx = Q.state.list[Q.state.cur];
  if (!Q.state.chapterResults[idx]) Q.pick(Q.chItems()[idx].answer);
  Q.chNext();
}
ok(Q.state.view === 'chapter-done', '再刷一遍可再次完成');
ok((Q.progress().chapters || {})[1].best.right === Q.CH[0].total, '全对后最佳成绩刷新为满分');

// 再刷出差成绩：不覆盖最佳
Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'ch-again' : null) });
let g5 = 0;
while (Q.state.view === 'chapter' && g5++ < 200) {
  const idx = Q.state.list[Q.state.cur];
  if (!Q.state.chapterResults[idx]) {
    const right = Q.chItems()[idx].answer;
    Q.pick(idx === 3 ? ['A', 'B', 'C', 'D'].find(k => k !== right) : right);
  }
  Q.chNext();
}
ok(Q.state.view === 'chapter-done', '第三次也能正常交卷');
ok((Q.progress().chapters || {})[1].best.right === Q.CH[0].total, '刷出差成绩不会覆盖最佳成绩');

Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'chapters' : null) });
h = HTML_APP();
ok(h.indexOf('最佳 ' + Q.CH[0].total + '/' + Q.CH[0].total) >= 0, '章节列表回显最佳成绩');
ok((h.match(/class="chcard is-done/g) || []).length === 1, '刷满分的章卡标记为已完成');

// 换一章：状态重置、标题跟着换
const chapBefore = Q.state.chapterIdx;
Q.openChapter(4);
h = HTML_APP();
ok(Q.state.chapterIdx === 4 && chapBefore !== 4, '可以切换到另一章');
ok(Object.keys(Q.state.chapterResults).length === 0, '换章后清空上一章作答');
ok(h.indexOf(Q.CH[4].name) >= 0, '换章后标题跟着换');
ok(h.indexOf('第 ' + Q.CH[4].objs[0].set + ' 套 · 第 ' + Q.CH[4].objs[0].no + ' 题') >= 0,
  '换章后第 1 题的来源角标同步更新');

Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'chapters' : null) });
Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'chapter' : (n === 'data-ch' ? '999' : null)) });
ok(Q.state.view === 'chapters', '非法章号被忽略，不会跳进空白页');
Q.openChapter(-1);
ok(Q.state.view === 'chapters', '负数章号同样被忽略');

Q.handleAct({ getAttribute: n => (n === 'data-act' ? 'home' : null) });
h = HTML_APP();
ok(!G('authorBadge').classList.contains('hidden'), '回到首页署名徽标重新出现');
ok(h.indexOf('按知识点刷题') >= 0, '首页仍保留章节入口');

/* ---------------- 手机端精简（APK / 窄屏只留做题与解析） ---------------- */
const wKeep = ctx.innerWidth;
ctx.innerWidth = 390;
ok(Q.isPhoneWidth() === true, '窄屏（≤620）识别为手机端');
ctx.innerWidth = 1200;
ok(Q.isPhoneWidth() === false, '宽屏不按手机端处理');
ctx.innerWidth = wKeep;

ok(html.indexOf('.hide-phone{display:none') > 0, '产物含「手机上隐藏」样式类');
ok(html.indexOf('.home-hero{display:none') > 0, '手机上收起首页标题块（顶栏已有名字，不重复）');
ok(HTML_APP().indexOf('home-hero') > 0, '首页 hero 带手机端标记');
ok(HTML_APP().indexOf('class="chip hide-phone"') > 0, '首页次要统计（总题量/每组）在手机上收起');
ok(HTML_APP().indexOf('chipbtn hide-phone') > 0, '玩法引导入口在手机上收起');
ok(HTML_APP().indexOf('class="setcard') > 0, '套卡本身照常显示（入口不受影响）');
ok(html.indexOf('.setcard .score,.setcard .drillscore{display:none') > 0, '套卡上的星级/直刷成绩在手机上收起');

// 手机上不弹 7 步引导，宽屏照旧
delete store['quiz_onboard_v1'];
ctx.innerWidth = 390;
Q.maybeShowOnboard();
ok(Q.onboardOn() === false, '手机上打开不弹分步引导');
ctx.innerWidth = 1200;
Q.maybeShowOnboard();
ok(Q.onboardOn() === true, '宽屏仍会弹分步引导');
Q.closeOnboard();
ctx.innerWidth = wKeep;

/* ---------------- 结果 ---------------- */
console.log('\n通过 ' + pass + ' 项，失败 ' + failures.length + ' 项');
if (failures.length) {
  console.log('\n失败明细：');
  failures.forEach(f => console.log('  ✗ ' + f));
  process.exit(1);
}
console.log('全部断言通过 ✓');
