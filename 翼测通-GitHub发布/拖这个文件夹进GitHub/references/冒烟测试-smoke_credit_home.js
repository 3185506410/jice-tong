/* 冀测通 v2 冒烟：jsdom runScripts:'dangerously' 真实执行页面脚本
 * 跑法：node smoke_v2.js
 * 期望值全部独立手算，不从页面读取后再比对。 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const HTML_PATH = process.env.DEMO_HTML ||
  [path.join(__dirname, '..', '学业记录.html'), path.join(__dirname, '..', 'assets', '学业记录.html')]
    .find(x => fs.existsSync(x));
if (!HTML_PATH) { console.error('找不到 学业记录.html（可用 DEMO_HTML 环境变量指定）'); process.exit(2); }
const HTML = fs.readFileSync(HTML_PATH, 'utf-8');

let pass = 0, fail = 0;
const ok = (cond, name) => {
  if (cond) { pass++; console.log('  ok ' + name); }
  else { fail++; console.log('  FAIL ' + name); }
};
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously',
    url: 'https://jice.test/#demo=1',
    pretendToBeVisual: true,
  });
  const { window } = dom;
  const { document } = window;
  await sleep(80); // 等脚本与 FileReader
  window.eval('window.__T = {UI, S: () => S, DATA, totalScore, ARCH, gpaSample}'); // const 不挂 window，需桥接

  /* ---- 一、结构：导入区、总分置顶、tile ---- */
  console.log('[一] 结构');
  const bar = document.querySelector('.importbar');
  ok(!!bar, '顶部固定导入区存在');
  const firstVisual = document.querySelector('.wrap > *');
  ok(firstVisual && firstVisual.classList.contains('importbar'), '导入区是内容区第一个元素（最上方入口）');
  ok(bar.textContent.includes('txt 直接存档'), '导入区文案为诚实口径（txt 直接存档）');
  ok(!document.body.textContent.includes('识别后归入对应条目'), '旧的超口径文案已删除');
  ok(document.getElementById('sc-course').textContent.includes('粘贴解析'), '课程页有粘贴解析入口');

  const total = document.getElementById('totalNum').textContent;
  ok(total.startsWith('103.8'), '综测总分 103.8（展示值复算：德育 100×.1 + 体育 88×.1 + 美育 97×.05 + 劳育 95.2×.05 + xs 15 + 绩点 89.1×.7 − 扣 2）');
  const hero = document.getElementById('sc-home').querySelector('.hero');
  ok(!!hero && hero.textContent.includes('学术科技 ×1.0') && hero.textContent.includes('绩点 ×0.7'),
    '总分旁有效率对比提示（学术科技 ×1.0 / 绩点 ×0.7）');
  ok(hero && hero.textContent.includes('美育 / 劳育 ×0.05'), '效率提示含美育/劳育 ×0.05');

  const tiles = [...document.querySelectorAll('#tiles .tile')];
  ok(tiles.length === 6, 'tile 共 6 块（绩点+四模块+学术科技通栏）');
  ok(tiles[0].textContent.includes('绩点') && tiles[0].textContent.includes('占 70%'), '第 1 块是绩点·占 70%');
  ok(tiles[5].textContent.includes('学术科技') && tiles[5].textContent.includes('不进五育加权'), '学术科技单设卡注明不进加权');

  /* ---- 二、绩点下钻：列表 → 课程 → 平时/期末 ---- */
  console.log('[二] 绩点下钻');
  tiles[0].click();
  ok(document.getElementById('sc-gpa').classList.contains('act'), '点绩点 tile 进入课程列表屏');
  const rows = [...document.querySelectorAll('#courseRows .row')];
  ok(rows.length === 4, '课程列表 4 门');
  ok(rows[0].textContent.includes('高等数学 A') && rows[0].textContent.includes('86.6'),
    '高数 A 课程成绩 86.6（86×60%+87.4×40%）');
  rows[0].click();
  ok(document.getElementById('sc-course').classList.contains('act'), '点课程行进入课程屏');
  ok(document.getElementById('partSum').textContent === '平时分 87.4', '平时分 87.4（(95×20+88×30+84×50)/100）');
  ok(document.getElementById('finalSum').textContent === '期末 86', '期末 86');
  const compInputs = [...document.querySelectorAll('#partItems input')];
  ok(compInputs.length === 3, '平时分 3 个独立条目（出勤/作业/期末小测）');
  ok(document.getElementById('cFormula').textContent.includes('86.6'), '课程成绩算式 86.6 照抄展示');

  /* ---- 三、模块条目计分 → 板块分（细则：基础分+附加封顶） ---- */
  console.log('[三] 模块条目计分');
  window.__T.UI.openMod('de');
  ok(document.getElementById('sc-mod').classList.contains('act'), '打开德育模块屏');
  ok(document.getElementById('mScoreT').textContent === '100.0 分',
    '德育初始 100.0（基础 75 + min(90%×115, 25)）');
  ok(document.getElementById('mSub').textContent.includes('基础分（自填，最高 75）'), '德育副标题：基础分自填、最高 75 口径');
  window.__T.UI.openMod('ti');
  const tiItems = [...document.querySelectorAll('#mItems input')];
  ok(document.getElementById('mScoreT').textContent === '88.0 分', '体育初始 88.0（35.2+35.2+17.6，无基础分）');
  tiItems[0].value = '0';
  tiItems[0].dispatchEvent(new window.Event('input', { bubbles: true }));
  ok(document.getElementById('mScoreT').textContent === '52.8 分',
    '体测改 0 后体育板块分 = 52.8（Σ条目直加重算）');
  ok(document.getElementById('mWeight').textContent.includes('计入总分'),
    '显示计入总分的加权值');
  const srcBtn = document.querySelector('#mItems .src');
  srcBtn.click();
  ok(document.getElementById('mask').classList.contains('show'), '点「来源」弹出回溯弹窗');
  ok(document.getElementById('modal').textContent.includes('条款坐标'), '弹窗含条款坐标');
  ok(document.getElementById('modal').textContent.includes('出处文件'), '弹窗含出处文件');
  window.__T.UI.close();

  /* ---- 四、材料导入 ---- */
  console.log('[四] 材料导入');
  const before = window.__T.S().years['大一'].materials.length;
  window.__T.UI.readFiles([new window.File(['出勤 20% 95分'], 'a.txt')]);
  await sleep(60);
  ok(window.__T.S().years['大一'].materials.length === before + 1, 'txt 文件读入并归档');
  window.__T.UI.readFiles([new window.File([], '证书.jpg')]);
  const jpg = window.__T.S().years['大一'].materials[0];
  ok(jpg.name === '证书.jpg' && !jpg.text, '非文本文件只登记名称不读内容');
  ok(before === 2, '演示数据自带 2 份材料');

  /* ---- 五、年级切换与空态 ---- */
  console.log('[五] 年级切换');
  window.__T.UI.setYear('大二');
  ok(document.getElementById('totalLab').textContent.includes('大二'), '切到大二');
  window.__T.UI.go('gpa');
  ok(document.getElementById('courseRows').textContent.includes('还没有课程'), '大二无课程显示空态');
  const t2 = window.__T.totalScore();
  const exp2 = 10 + 8.8 + 4.85 + 4.76 + 15; // 无绩点课程、无扣分
  ok(Math.abs(t2 - exp2) < 0.06, '大二总分 = 43.4（绩点空缺按 0，不猜；' + exp2 + '）');

  /* ---- 六、主题 ---- */
  console.log('[六] 主题');
  window.__T.UI.toggleTheme();
  ok(document.documentElement.dataset.theme === 'dark', '切换到暗色');
  window.__T.UI.toggleTheme();
  ok(document.documentElement.dataset.theme === 'calm', '切回浅色');

  /* ---- 八九十：全新页面实例（干净状态：大一数据、首访建档窗完好） ---- */
  console.log('[八] GPA 示例 / [九] 学分明细 / [十] 综测档案袋（全新实例）');
  const dom2 = new JSDOM(HTML, { runScripts: 'dangerously', url: 'https://jice2.test/#demo=1&gate=1', pretendToBeVisual: true });
  await sleep(80);
  const W2 = dom2.window, D2 = W2.document;
  W2.eval('window.__T2 = {UI, S: () => S, DATA, totalScore, ARCH, gpaSample}');
  const T2 = W2.__T2;

  /* [八] GPA 示例卡 */
  T2.UI.go('gpa');
  const gsBox = D2.getElementById('gpaSampleBox').textContent;
  ok(gsBox.includes('3.91'), 'GPA 示例 3.91（示例规则按学分加权）');
  ok(gsBox.includes('示例'), '标注「示例」小标');
  ok(gsBox.includes('学生手册'), '引导上传《学生手册》按原文替换');

  /* [九] 学分明细 */
  T2.UI.go('credits');
  const cw = D2.getElementById('creditsWrap');
  ok(cw.querySelectorAll('.sz').length === T2.DATA.groups.length, '学分表按分组渲染（' + T2.DATA.groups.length + ' 组）');
  ok(cw.querySelectorAll('.sz tbody tr').length === 16, '16 个模块逐条成行');
  ok(cw.textContent.includes('两处方案自相矛盾'), '两处矛盾照实呈现');
  ok(cw.querySelectorAll('.conflict').length === 2, '矛盾卡片 2 张');
  T2.UI.setCreditMod('思想政治理论课', 18);
  ok(T2.S().years['大一'].creditMods['思想政治理论课'] === 18, '已修学分可填存');

  /* [十] 档案袋：建档→上传→匹配→同步→总分联动 */
  ok(D2.getElementById('mask').classList.contains('show'), '首访弹出建档窗');
  ok(!!D2.getElementById('pmGrade') && !!D2.getElementById('pmCohort'), '建档窗含年级/入学级两组选项');
  D2.querySelector('#pmGrade .m-opt').click();
  D2.querySelector('#pmCohort .m-opt').click();
  T2.ARCH.saveProfile();
  ok(!!W2.localStorage.getItem('jice_profile_v1'), '建档写入 jice_profile_v1');
  ok(!D2.getElementById('mask').classList.contains('show'), '建档后弹窗关闭');

  T2.ARCH.openUpload();
  ok(!!D2.getElementById('upType'), '上传窗渲染');
  D2.getElementById('upType').value = 'comp';
  T2.ARCH.onTypeChange();
  ok(!!D2.getElementById('f_level'), '竞赛类型动态字段渲染（六级表）');
  D2.getElementById('f_level').value = '国甲类';
  D2.getElementById('f_prize').value = '一等';
  D2.getElementById('f_place').value = '1';
  D2.getElementById('upName').value = '数模国赛一等奖';
  T2.ARCH.saveMaterial();
  let items = T2.S().years['大一'].arch.items;
  ok(items.length === 1, '材料入库 1 件');
  ok(items[0].state === '确定' && items[0].score === 20,
    '国甲类一等·队内第 1 → 20 分（细则第六条（六）4，单项封顶 20）');
  ok((items[0].clause || '').includes('第六条'), '条款坐标已记录');

  /* 待核路径：讲座分值未结构化 */
  T2.ARCH.openUpload();
  D2.getElementById('upType').value = 'lecture';
  T2.ARCH.onTypeChange();
  D2.getElementById('upName').value = '讲座打卡×3';
  T2.ARCH.saveMaterial();
  items = T2.S().years['大一'].arch.items;
  ok(items.length === 2 && items[1].state === '待核' && items[1].score === 0,
    '讲座材料「待核」暂计 0，不猜');

  const before3 = T2.totalScore();
  T2.ARCH.syncToLedger();
  ok(T2.S().years['大一'].arch.xs === 20, '同步后账本 xs 附加 +20');
  ok(items[0].state === '已同步' && items[0].syncedScore === 20, '材料标记已同步');
  ok(items[1].state === '待核', '待核材料不同步');
  const xsAfter = Math.min(15 + 20, 20);
  ok(Math.abs(T2.totalScore() - (before3 + (xsAfter - 15))) < 0.06,
    '总分联动：xs 15→20 封顶，总分 ' + before3.toFixed(1) + '→' + T2.totalScore().toFixed(1));

  /* zip 字节结构：crc32 对拍 zlib，makeZip 长度手算 */
  const zlib = require('zlib');
  const u8 = T2.ARCH.str2u8('hello 世界');
  ok(T2.ARCH.crc32(u8) === zlib.crc32(Buffer.from('hello 世界', 'utf-8')), 'crc32 与 Node zlib 对拍一致');
  const blob = T2.ARCH.makeZip([{name: 'a.txt', data: u8}]);
  ok(blob.size === (30 + 5) + 12 + (46 + 5) + 22, 'zip 结构长度 = 本地头 35 + 数据 12 + 中央目录 51 + EOCD 22 = 120');

  /* ---- 七、换行格式 ---- */
  console.log('[七] 文件格式');
  const raw = fs.readFileSync(HTML_PATH, null);
  ok(!raw.includes('\r\n'), '产物为纯 LF（无 CRLF）');

  console.log('\n结果: ' + pass + ' 过 / ' + fail + ' 挂');
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('冒烟异常:', e); process.exit(2); });
