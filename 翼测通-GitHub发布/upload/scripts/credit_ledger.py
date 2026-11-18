# -*- coding: utf-8 -*-
"""学分账本 · 学分缺口核算 + 本学期任务清单

只做加法、比对与机械推演，不做任何推测。

用法：
    python credit_ledger.py ledger.json taken.json      # 正常核算（学期从 ledger.current_term 取）
    python credit_ledger.py ledger.json taken.json --term 3   # 手动指定当前学期
    python credit_ledger.py --demo                      # 用内置样例演示（含四步全部输出）

ledger.json  —— 从培养方案拆出来的账（见 SKILL.md「拆账」）
                可带 current_term / total_terms / extra_tasks
taken.json   —— 学生已修课程
"""
import json
import re
import sys

# 名称归一化：去掉空格、统一括号、统一大小写
# 「高等数学A(上)」与「高等数学 A（上）」归一化后应当相等
def norm(s):
    s = str(s or "")
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace(" ", "").replace("\t", "")
    return s.upper()


def match_course(name, courses):
    """返回 (matched_course, how)。how ∈ exact / norm / suspect / none"""
    n = norm(name)
    for c in courses:
        if str(c.get("name", "")) == str(name):
            return c, "exact"
    for c in courses:
        if norm(c.get("name")) == n:
            return c, "norm"
    # 疑似：一方包含另一方，且不短于 3 个字（短词包含会大面积误命中）
    for c in courses:
        cn = norm(c.get("name"))
        if len(cn) >= 3 and len(n) >= 3 and (cn in n or n in cn):
            return c, "suspect"
    return None, "none"


def ledger_of(ledger):
    return ledger.get("courses") or []


def compute(ledger, taken):
    courses = ledger_of(ledger)
    cats = ledger.get("categories") or []
    earned = {c.get("name"): 0.0 for c in cats}
    hits, suspects, outside = [], [], []

    for t in taken:
        nm = t.get("name")
        cr = float(t.get("credits") or 0)
        c, how = match_course(nm, courses)
        if how == "none":
            outside.append({"name": nm, "credits": cr})
            continue
        if how == "suspect":
            # 疑似不计入，交给人判断
            suspects.append({"taken": nm, "plan": c.get("name"), "credits": cr})
            continue
        cat = c.get("category")
        if cat not in earned:
            earned[cat] = 0.0
        earned[cat] += cr
        hits.append({"taken": nm, "plan": c.get("name"), "credits": cr, "category": cat})

    rows = []
    for c in cats:
        nm = c.get("name")
        req = c.get("required")
        low = c.get("min")
        need = float(req) if isinstance(req, (int, float)) else None
        got = round(earned.get(nm, 0.0), 2)
        if need is None and isinstance(low, (int, float)):
            need = float(low)
        gap = None if need is None else round(max(0.0, need - got), 2)
        rows.append({"name": nm, "need": need, "got": got, "gap": gap})

    total_need = sum(r["need"] for r in rows if r["need"] is not None)
    total_got = round(sum(r["got"] for r in rows), 2)
    return {
        "rows": rows,
        "total_need": round(total_need, 2),
        "total_got": total_got,
        "total_gap": round(max(0.0, total_need - total_got), 2),
        "hits": hits,
        "suspects": suspects,
        "outside": outside,
    }


# ---------- 第四步 · 排任务 ----------
# 把「账」变成「这学期该干什么」。
# 后果文案只有三条合法来源：开课学期 / 先修关系 / 总学分线。除此之外一律不写。

MAX_TASKS = 6


def _term_no(text):
    """从「第 3 学期」这类文本里取学期号；取不到返回 None。"""
    m = re.search(r"第\s*(\d+)\s*学期", str(text or ""))
    return int(m.group(1)) if m else None


def remaining_terms(current_term, total_terms=8):
    return max(0, int(total_terms) - int(current_term) + 1)


def plan_tasks(ledger, r, current_term, total_terms=8, extra_tasks=None):
    """返回 (任务列表, 是否被截断, 截断前的总数)。"""
    courses = ledger_of(ledger)
    passed = {norm(h["plan"]) for h in r["hits"]}

    successors = {}
    for c in courses:
        for p in (c.get("prerequisite") or []):
            successors.setdefault(norm(p), []).append(c.get("name"))

    tasks = []

    # A · 本学期开课、且尚未修完的课
    for c in courses:
        if _term_no(c.get("term")) != int(current_term):
            continue
        if norm(c.get("name")) in passed:
            continue
        why = "第 %d 学期开课" % int(current_term)
        if c.get("category"):
            why = "%s，%s" % (c["category"], why)
        miss = [p for p in (c.get("prerequisite") or []) if norm(p) not in passed]
        if miss:
            conseq = "先修「%s」未通过，本课排不进本学期" % "、".join(miss)
        else:
            nxt = successors.get(norm(c.get("name")), [])
            if nxt:
                conseq = "不修则「%s」不能排" % "、".join(nxt)
            else:
                conseq = "这门课只在第 %d 学期开，错过要等下一轮" % int(current_term)
        tasks.append({
            "task": "修「%s」（%s 学分）" % (c.get("name"), fnum(c.get("credits"))),
            "why": why,
            "consequence": conseq,
            "source": c.get("source") or ("课程计划表 · %s" % c.get("term", "")),
            "deadline": "本学期选课",
            "kind": "course",
        })

    # B · 分类缺口摊到剩余学期
    rem = remaining_terms(current_term, total_terms)
    if rem > 0:
        for row in sorted([x for x in r["rows"] if x.get("gap")], key=lambda x: -x["gap"]):
            per = round(row["gap"] / rem, 2)
            tasks.append({
                "task": "补「%s」≥ %s 学分" % (row["name"], fnum(per)),
                "why": "该类缺口 %s 学分，还剩 %d 个学期" % (fnum(row["gap"]), rem),
                "consequence": "毕业资格审查时该类不达标",
                "source": "毕业要求总表 / 课程设置",
                "deadline": "本学期选课",
                "kind": "category",
            })

    # C · 外部规则带来的任务（综测细则等）——只在用户真的提供了细则时才传进来
    for e in (extra_tasks or []):
        tasks.append({
            "task": e.get("task", ""),
            "why": e.get("why", ""),
            "consequence": e.get("consequence", ""),
            "source": e.get("source", ""),
            "deadline": e.get("deadline", ""),
            "kind": "rule",
        })

    total = len(tasks)
    # 排序优先级：本学期具体课程 > 外部规则（综测等）> 分类缺口（聚合派生，最可省）
    rank = {"course": 0, "rule": 1, "category": 2}
    tasks.sort(key=lambda t: rank.get(t.get("kind"), 9))
    return tasks[:MAX_TASKS], total > MAX_TASKS, total


def fnum(x):
    if x is None:
        return "—"
    return ("%g" % x)


def report(ledger, taken, r, tasks=None, current_term=None,
           clipped=False, total_tasks=0, has_rules=False):
    out = []
    out.append("# 学分账本 · 核算结果")
    out.append("")
    out.append("专业：%s　年级：%s" % (ledger.get("major", "未填"), ledger.get("year", "未填")))
    out.append("")
    if ledger.get("_demo"):
        out.append("> **本样例只摘录了 12 门课**（真实培养方案通常 40~60 门），"
                   "所以「已修」偏少、缺口偏大。这是摘录造成的，不是算错。")
        out.append("> 真实使用时，请把整份培养方案的课程表全部拆进来再跑。")
        out.append("")
    out.append("## 一、学分总览")
    out.append("")
    out.append("培养方案要求 **%s** 学分，已修 **%s** 学分，还差 **%s** 学分。"
               % (fnum(r["total_need"]), fnum(r["total_got"]), fnum(r["total_gap"])))
    out.append("")
    out.append("| 类别 | 要求 | 已修 | 缺口 |")
    out.append("|---|---|---|---|")
    for row in r["rows"]:
        out.append("| %s | %s | %s | %s |"
                   % (row["name"], fnum(row["need"]), fnum(row["got"]), fnum(row["gap"])))
    out.append("")
    out.append("## 二、已匹配上的课（%d 门）" % len(r["hits"]))
    out.append("")
    for h in r["hits"]:
        out.append("- %s → %s（%s 学分，%s）" % (h["taken"], h["plan"], fnum(h["credits"]), h["category"]))
    out.append("")
    out.append("## 三、需要你确认的（系统不替你判断）")
    out.append("")
    if r["suspects"]:
        out.append("**疑似对应，未计入缺口：**")
        out.append("")
        for s in r["suspects"]:
            out.append("- 成绩单「%s」疑似对应方案里「%s」——请确认是不是同一门。" % (s["taken"], s["plan"]))
    else:
        out.append("（无疑似项）")
    out.append("")
    if r["outside"]:
        out.append("**方案外课程，未计入缺口：**")
        out.append("")
        for o in r["outside"]:
            out.append("- %s（%s 学分）在培养方案中未找到对应项。" % (o["name"], fnum(o["credits"])))
    else:
        out.append("（无方案外课程）")
    out.append("")

    if current_term and tasks is not None:
        out.append("## 本学期制度性任务清单（第 %d 学期）" % int(current_term))
        out.append("")
        if tasks:
            out.append("| # | 任务 | 为什么必须做 | 不做会怎样 | 依据 | 截止 |")
            out.append("|---|---|---|---|---|---|")
            for i, t in enumerate(tasks, 1):
                out.append("| %d | %s | %s | %s | %s | %s |"
                           % (i, t["task"], t["why"], t["consequence"], t["source"], t["deadline"]))
            out.append("")
            out.append("本学期共 %d 件。做完即达成。" % len(tasks))
            if clipped:
                out.append("")
                out.append("> 另有 %d 件未列出。**清单太长等于没有清单**，"
                           "只保留最要紧的 %d 件。" % (total_tasks - len(tasks), MAX_TASKS))
        else:
            out.append("本学期没有制度上必须完成的事。")
        out.append("")
        # 只有综测类任务真的进了清单，才提示去核对细则
        if any(t.get("kind") == "rule" for t in tasks):
            out.append("**需要你确认的**：上表带「细则」依据的行来自综测细则，"
                       "各学院口径不一，请核对是不是你所在学院这一版。")
        else:
            out.append("**需要你确认的**：未提供综测细则，故**不含综测类任务**——"
                       "没有细则我算不出来，不猜。")
        out.append("")
        out.append("> 本清单只含**规则要求必须做**的事，不含任何「我想做」的事。")
        out.append("> 本技能**不主动推送**：有需要时来 `@` 一下即可。")
        out.append("")
    elif tasks is None:
        out.append("## 本学期制度性任务清单")
        out.append("")
        out.append("**未生成**——要排任务，需要先告诉我「你现在第几学期」（如 `--term 3`）。"
                   "不知道学期，排出来的任务全是错的。")
        out.append("")

    return "\n".join(out)


DEMO_LEDGER = {
    "_demo": True,
    "major": "智能科学与技术（示例）",
    "year": "2026 级（示例数据，非真实培养方案）",
    "current_term": 3,
    "total_terms": 8,
    "categories": [
        {"name": "通识必修", "required": 42},
        {"name": "专业必修", "required": 58},
        {"name": "专业选修", "min": 40},
        {"name": "实践环节", "required": 30},
    ],
    "courses": [
        {"name": "高等数学A(上)", "credits": 5, "category": "通识必修", "term": "第 1 学期",
         "source": "第 7 页 课程计划表 第 1 行"},
        {"name": "高等数学A(下)", "credits": 5, "category": "通识必修", "term": "第 2 学期",
         "source": "第 7 页 课程计划表 第 2 行"},
        {"name": "大学英语(一)", "credits": 3, "category": "通识必修", "term": "第 1 学期",
         "source": "第 7 页 课程计划表 第 3 行"},
        {"name": "线性代数", "credits": 3, "category": "通识必修", "term": "第 2 学期",
         "source": "第 7 页 课程计划表 第 4 行"},
        {"name": "程序设计基础", "credits": 4, "category": "专业必修", "term": "第 1 学期",
         "source": "第 7 页 课程计划表 第 5 行"},
        {"name": "数据结构与算法", "credits": 4, "category": "专业必修", "term": "第 3 学期",
         "prerequisite": ["程序设计基础"], "source": "第 7 页 课程计划表 第 6 行"},
        {"name": "概率论与数理统计", "credits": 3, "category": "专业必修", "term": "第 3 学期",
         "prerequisite": ["线性代数"], "source": "第 7 页 课程计划表 第 7 行"},
        {"name": "操作系统", "credits": 4, "category": "专业必修", "term": "第 5 学期",
         "prerequisite": ["数据结构与算法"], "source": "第 7 页 课程计划表 第 8 行"},
        {"name": "计算机网络", "credits": 3, "category": "专业必修", "term": "第 5 学期",
         "source": "第 7 页 课程计划表 第 9 行"},
        {"name": "机器学习", "credits": 3, "category": "专业选修", "term": "第 5 学期",
         "source": "第 7 页 课程计划表 第 10 行"},
        {"name": "军训", "credits": 2, "category": "实践环节", "term": "第 1 学期",
         "source": "第 9 页 实践教学环节表 第 1 行"},
        {"name": "毕业设计", "credits": 12, "category": "实践环节", "term": "第 8 学期",
         "source": "第 9 页 实践教学环节表 第 2 行"},
    ],
}

# 综测细则带来的任务。**只有用户真的提供了细则，才允许填这一项**，否则留空。
DEMO_EXTRA = [
    {"task": "参加 ≥ 1 项学科竞赛",
     "why": "综测细则「创新实践」项按获奖等级计分",
     "consequence": "该项计 0 分，综测排名受影响",
     "source": "综测细则（示例）第 3 页 第 4 条",
     "deadline": "按赛事公告"},
]

DEMO_TAKEN = [
    {"name": "高等数学A(上)", "credits": 5},
    {"name": "高等数学 A（下）", "credits": 5},
    {"name": "大学英语(一)", "credits": 3},
    {"name": "程序设计基础", "credits": 4},
    {"name": "数据结构", "credits": 4},
    {"name": "军训", "credits": 2},
    {"name": "创新创业实践", "credits": 2},
]


def self_check():
    """三态自检：正常 / 边界 / 数据完整性。打印 N/N，任一不过即非 0 退出。"""
    cases = []

    def chk(state, name, got, want):
        cases.append((state, name, got, want))

    r = compute(DEMO_LEDGER, DEMO_TAKEN)
    courses = DEMO_LEDGER["courses"]

    # ---- 正常：已知课程匹配与学分汇总 ----
    chk("正常", "总要求 = 42+58+40+30 = 170", r["total_need"], 170)
    chk("正常", "已修 = 5+5+3+4+2 = 19", r["total_got"], 19)
    chk("正常", "缺口 = 170-19 = 151", r["total_gap"], 151)
    chk("正常", "通识必修已修 13（高数上5+高数下5+大英3）",
        [x for x in r["rows"] if x["name"] == "通识必修"][0]["got"], 13)
    chk("正常", "专业必修已修 4（程序设计基础）",
        [x for x in r["rows"] if x["name"] == "专业必修"][0]["got"], 4)
    chk("正常", "专业选修按 min=40 记缺口", 
        [x for x in r["rows"] if x["name"] == "专业选修"][0]["gap"], 40)
    chk("正常", "命中 5 门", len(r["hits"]), 5)
    chk("正常", "全角/空格差异仍能归一匹配",
        match_course("高等数学 A（下）", courses)[1], "norm")
    chk("正常", "第 3 学期取到学期号 3", _term_no("第 3 学期"), 3)
    chk("正常", "剩余学期 = 8-3+1 = 6", remaining_terms(3, 8), 6)
    chk("正常", "任务清单不超过 MAX_TASKS", 
        len(plan_tasks(DEMO_LEDGER, r, 3, 8, DEMO_EXTRA)[0]), MAX_TASKS)
    chk("正常", "报告含学分总览", "学分总览" in report(
        DEMO_LEDGER, DEMO_TAKEN, r), True)

    # ---- 边界：必须交给人判断，不许自动计入 ----
    chk("边界", "「数据结构」→ 疑似，不计入", 
        match_course("数据结构", courses)[1], "suspect")
    chk("边界", "疑似项只进 suspects 不进 hits", len(r["suspects"]), 1)
    chk("边界", "方案外课程「创新创业实践」进 outside", 
        [o["name"] for o in r["outside"]], ["创新创业实践"])
    chk("边界", "方案外课程不计入任何类别已修", r["total_got"], 19)
    chk("边界", "查不到的课 → none", 
        match_course("大学物理（二）", courses)[1], "none")
    chk("边界", "学期文本取不到 → None", _term_no(""), None)
    chk("边界", "空成绩单 → 已修 0", 
        compute(DEMO_LEDGER, [])["total_got"], 0)
    chk("边界", "空成绩单 → 无命中无方案外", 
        (len(compute(DEMO_LEDGER, [])["hits"]),
         len(compute(DEMO_LEDGER, [])["outside"])), (0, 0))
    chk("边界", "空培养方案 → 要求 0", 
        compute({"categories": [], "courses": []}, DEMO_TAKEN)["total_need"], 0)

    # ---- 数据完整性：常量表与样例自洽 ----
    chk("完整", "样例四类学分要求齐全",
        sorted(x["name"] for x in DEMO_LEDGER["categories"]),
        sorted(["通识必修", "专业必修", "专业选修", "实践环节"]))
    chk("完整", "样例课程 12 门", len(courses), 12)
    chk("完整", "样例已修 7 条", len(DEMO_TAKEN), 7)
    chk("完整", "清单上限 = 6（太长等于没有清单）", MAX_TASKS, 6)
    chk("完整", "总缺口 = 各类缺口之和",
        r["total_gap"], sum(x["gap"] for x in r["rows"]))

    ok = 0
    for state, name, got, want in cases:
        good = got == want
        ok += good
        print("%s [%s] %s　实际=%r 预期=%r"
              % ("✓" if good else "✗", state, name, got, want))
    print("")
    print("自检结果：%d/%d 通过" % (ok, len(cases)))
    return ok == len(cases)


def main():
    args = list(sys.argv[1:])
    if args and args[0] == "--self-check":
        sys.exit(0 if self_check() else 1)
    term = None
    if "--term" in args:
        i = args.index("--term")
        try:
            term = int(args[i + 1])
        except (IndexError, ValueError):
            print("--term 后面要跟学期号，例如 --term 3")
            return
        del args[i:i + 2]

    if args and args[0] == "--demo":
        ledger, taken = DEMO_LEDGER, DEMO_TAKEN
        extra = DEMO_EXTRA
        if term is None:
            term = ledger.get("current_term")
    elif len(args) >= 2:
        try:
            with open(args[0], encoding="utf-8") as f:
                ledger = json.load(f)
            with open(args[1], encoding="utf-8") as f:
                taken = json.load(f)
        except OSError as e:
            print("读不到输入文件：%s" % (e.filename or e))
            return
        except ValueError as e:
            print("输入文件不是合法 JSON（%s）" % e)
            return
        extra = ledger.get("extra_tasks")
        if term is None:
            term = ledger.get("current_term")
    else:
        print(__doc__)
        return

    r = compute(ledger, taken)
    tasks = clipped = total = None
    if term:
        tasks, clipped, total = plan_tasks(
            ledger, r, term, ledger.get("total_terms", 8), extra)
    print(report(ledger, taken, r, tasks, term, clipped, total, bool(extra)))


if __name__ == "__main__":
    main()
