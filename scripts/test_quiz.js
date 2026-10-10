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

/* ---------------- 首次打开的排版引导 ---------------- */
ok(typeof Q.maybeShowLayoutTip === 'function' && typeof Q.closeLayoutTip === 'function',
  '引导相关 API 已暴露');
ok(Q.layoutTipDone() === false, '全新环境：引导还没看过');
ok(Q.layoutTipOn() === true, '首次打开（无任何本地记录）自动弹出排版引导');
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
// 以 output/images/set_XX/ 里实际有没有图为准，别把「第几套有图」写死 ——
// 每补一套图都要改测试的话，测试会因为数据变了而假失败。
const IMG_ROOT = path.join(__dirname, '..', 'images');
const pad2 = n => (n < 10 ? '0' + n : '' + n);
const setsWithImg = [], setsNoImg = [];
Q.SETS.forEach(s => {
  const has = [1, 2, 20].every(n => fs.existsSync(path.join(IMG_ROOT, 'set_' + pad2(s.set), n + '.png')));
  (has ? setsWithImg : setsNoImg).push(s);
});
ok(setsWithImg.length >= 1, '至少有一套已配图（实际 ' + setsWithImg.length + ' 套）');
ok(setsWithImg.every(s => s.items.length === 20), '已配图的套均为 20 题');
ok(setsWithImg.every(s => s.items.every(q => (q.image || '').indexOf('data:image/png;base64,') === 0)),
  '已配图的套：每题都内嵌了图片');
ok(setsWithImg.every(s => s.items.every(q => q.image.indexOf('iVBORw0KGgo') > 0)),
  '内嵌数据是合法 PNG（文件头校验通过）');
const imgLens = setsWithImg.reduce((a, s) => a.concat(s.items.map(q => q.image.length)), []);
ok(Math.min.apply(null, imgLens) > 30000,
  '每张配图体积正常（最小 ' + Math.round(Math.min.apply(null, imgLens) * 3 / 4 / 1024) + ' KB）');
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

/* ---------------- 结果 ---------------- */
console.log('\n通过 ' + pass + ' 项，失败 ' + failures.length + ' 项');
if (failures.length) {
  console.log('\n失败明细：');
  failures.forEach(f => console.log('  ✗ ' + f));
  process.exit(1);
}
console.log('全部断言通过 ✓');
