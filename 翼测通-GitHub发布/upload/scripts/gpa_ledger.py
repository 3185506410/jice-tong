# -*- coding: utf-8 -*-
"""绩点账 · 期末+平时两层加权 + 加权平均分

只做算术：Σ(得分×权重)÷Σ权重、期末×权重+平时×剩余、Σ(成绩×学分)÷Σ学分。
学分绩点 GPA 默认不换算（学校规则未提供）；加 --rule sample 可看内置示例规则的演示值，
输出明确标注「示例」，不是本校原文。不补 0、不猜缺项。

用法：
    python gpa_ledger.py --demo                 # 内置样例（4 门课）
    python gpa_ledger.py gpa.json               # 读自己的课程表
    python gpa_ledger.py gpa.json --term 3      # 只看第 3 学期
    python gpa_ledger.py --demo --rule sample   # 附带示例 GPA（明确标注示例）
    python gpa_ledger.py --self-check           # 自检（正常/边界/完整性）

gpa.json 格式：
{
  "courses": [
    {"name": "高等数学 A", "credit": 5, "term": 1, "final": 86, "finalW": 60,
     "comps": [{"name": "出勤", "weight": 20, "score": 95},
               {"name": "作业", "weight": 30, "score": 88}]}
  ]
}

口径出处：
    加权平均 = ∑(课程成绩×学分) ÷ ∑课程学分    ←《综合素质测评实施细则》（二）原文
    平时分/课程成绩 = 教师评分规则（各科不同，本脚本按用户给的权重归一）
    学分绩点 GPA = 学校换算规则；未提供时默认不换算，--rule sample 给出明确标注的示例值
"""
import json
import math
import sys

# ============================================================
# 口径常量（与界面同源，改一处必须改两处）
# ============================================================
FORMULA = "加权平均 = Σ(课程成绩×学分) ÷ Σ课程学分"
DEFAULT_FINAL_W = 60          # 没给权重时按期末 60% 算
CROSS_TERM_TO_GRADE = {1: "大一", 2: "大一", 3: "大二", 4: "大二",
                       5: "大三", 6: "大三", 7: "大四", 8: "大四"}


def _num(v):
    """转数字；转不了返回 None（不把 None 当 0）"""
    try:
        if v is None or v == "":
            return None
        x = float(v)
        if x != x or x in (float("inf"), float("-inf")):
            return None
        return x
    except (TypeError, ValueError):
        return None


def _r1(x):
    # 四舍五入（带容差）：与界面 Math.floor(x*10+0.5+1e-9)/10 保持同源
    return math.floor(x * 10 + 0.5 + 1e-9) / 10.0


def part_score(course):
    """平时分 = Σ(条目得分×条目权重) ÷ Σ条目权重；没有可算条目返回 None"""
    comps = course.get("comps") or []
    wsum = 0.0
    acc = 0.0
    for c in comps:
        w = _num(c.get("weight"))
        s = _num(c.get("score"))
        if w is None or s is None or w <= 0:
            continue
        wsum += w
        acc += s * w
    if wsum <= 0:
        return None
    return _r1(acc / wsum)


def course_score(course):
    """课程成绩 = 期末×期末权重% + 平时×(1−期末权重%)；缺期末或平时返回 None"""
    ps = part_score(course)
    if ps is None:
        return None
    f = _num(course.get("final"))
    if f is None:
        return None
    fw = _num(course.get("finalW"))
    if fw is None:
        fw = DEFAULT_FINAL_W
    fw = max(0.0, min(100.0, fw))
    return _r1(f * fw / 100.0 + ps * (100.0 - fw) / 100.0)


def weighted(courses, term=None):
    """加权平均；只算「有成绩且学分>0」的课。返回 dict"""
    sw = 0.0
    acc = 0.0
    done = 0
    skipped = []
    for c in courses:
        if term is not None:
            t = _num(c.get("term"))
            if t is None or int(t) != int(term):
                continue
        s = course_score(c)
        if s is None:
            skipped.append((c.get("name") or "(未命名)", "缺期末分或平时明细"))
            continue
        cr = _num(c.get("credit"))
        if cr is None or cr <= 0:
            skipped.append((c.get("name") or "(未命名)", "学分缺失或为 0，不计入加权"))
            continue
        sw += cr
        acc += s * cr
        done += 1
    if sw <= 0:
        return {"avg": None, "credit": 0.0, "done": 0, "skipped": skipped}
    return {"avg": _r1(acc / sw), "credit": _r1(sw), "done": done, "skipped": skipped}


SAMPLE_RULE_TEXT = "示例规则：绩点 =（课程成绩 − 50）÷ 10，60 分以下计 0（非本校原文，以《学生手册》为准）"


def sample_gpa(courses, term=None):
    """内置示例规则的 GPA 演示值。只为演示输出形态，不是本校规则。"""
    sw = 0.0
    acc = 0.0
    for c in courses:
        if term is not None:
            t = _num(c.get("term"))
            if t is None or int(t) != int(term):
                continue
        s = course_score(c)
        cr = _num(c.get("credit"))
        if s is None or cr is None or cr <= 0:
            continue
        sw += cr
        acc += (0.0 if s < 60 else (s - 50) / 10.0) * cr
    if sw <= 0:
        return None
    return math.floor(acc / sw * 100 + 0.5 + 1e-9) / 100.0


def term_table(courses):
    """按学期汇总，返回 [(学期号, 门数, 学分, 加权平均)]"""
    terms = sorted({int(_num(c.get("term"))) for c in courses
                    if _num(c.get("term")) is not None})
    out = []
    for t in terms:
        w = weighted(courses, t)
        n = sum(1 for c in courses if _num(c.get("term")) == t)
        out.append((t, n, w["credit"], w["avg"]))
    return out


def report(courses, term=None, rule=None):
    lines = []
    lines.append("绩点账" + ("（第 %s 学期）" % term if term is not None else "（全部学期）"))
    lines.append("=" * 66)
    head = "%-22s %5s %6s %6s %6s %7s" % ("课程", "学分", "期末", "期末%", "平时", "课程成绩")
    lines.append(head)
    lines.append("-" * 66)
    rows = 0
    for c in courses:
        if term is not None:
            t = _num(c.get("term"))
            if t is None or int(t) != int(term):
                continue
        name = (c.get("name") or "(未命名)")[:22]
        cr = _num(c.get("credit"))
        f = _num(c.get("final"))
        fw = _num(c.get("finalW"))
        fw = DEFAULT_FINAL_W if fw is None else max(0.0, min(100.0, fw))
        ps = part_score(c)
        s = course_score(c)
        lines.append("%-22s %5s %6s %6s %6s %7s" % (
            name,
            "%.1f" % cr if cr is not None else "—",
            "%.1f" % f if f is not None else "—",
            "%.0f%%" % fw,
            "%.1f" % ps if ps is not None else "待填",
            "%.1f" % s if s is not None else "待填"))
        rows += 1
    if rows == 0:
        lines.append("（没有课程）")
    lines.append("-" * 66)

    w = weighted(courses, term)
    if w["avg"] is None:
        lines.append("加权平均：算不出来——没有「期末分与平时明细都齐、且学分>0」的课程")
    else:
        lines.append("加权平均：%.1f 分（%d 门课，%.1f 学分）" % (w["avg"], w["done"], w["credit"]))
    if rule == "sample":
        g = sample_gpa(courses, term)
        if g is None:
            lines.append("学分绩点（GPA，示例规则）：算不出来——没有可算的课程")
        else:
            lines.append("学分绩点（GPA，示例规则）：%.2f" % g)
        lines.append("  ↑ %s" % SAMPLE_RULE_TEXT)
    else:
        lines.append("学分绩点（GPA）：待学校换算规则，本脚本不换算（要示例值加 --rule sample）")
    if w["skipped"]:
        lines.append("")
        lines.append("没计入加权平均的：")
        for name, why in w["skipped"]:
            lines.append("  - %s：%s" % (name, why))
    tt = term_table(courses)
    if len(tt) > 1:
        lines.append("")
        lines.append("分学期：")
        for t, n, cr, avg in tt:
            lines.append("  第 %d 学期（%s）：%d 门 / %.1f 学分 / 加权 %s"
                         % (t, CROSS_TERM_TO_GRADE.get(t, "?"), n, cr,
                            "%.1f" % avg if avg is not None else "待填"))
    lines.append("")
    lines.append("口径：%s" % FORMULA)
    return "\n".join(lines)


# ============================================================
# 自检：正常 / 边界 / 数据完整性
# ============================================================
DEMO = {
    "courses": [
        {"name": "高等数学 A", "credit": 5, "term": 1, "final": 86, "finalW": 60,
         "comps": [{"name": "出勤", "weight": 20, "score": 95},
                   {"name": "作业", "weight": 30, "score": 88},
                   {"name": "期末小测", "weight": 50, "score": 84}]},
        {"name": "大学英语（一）", "credit": 4, "term": 1, "final": 90, "finalW": 50,
         "comps": [{"name": "出勤", "weight": 20, "score": 96},
                   {"name": "作业", "weight": 40, "score": 90},
                   {"name": "口语", "weight": 40, "score": 88}]},
        {"name": "程序设计基础", "credit": 4, "term": 2, "final": 88, "finalW": 40,
         "comps": [{"name": "出勤", "weight": 10, "score": 100},
                   {"name": "实验", "weight": 40, "score": 92},
                   {"name": "课程设计", "weight": 50, "score": 90}]},
        {"name": "体育（一）", "credit": 1, "term": 2, "final": 92, "finalW": 30,
         "comps": [{"name": "出勤", "weight": 50, "score": 95},
                   {"name": "体测", "weight": 50, "score": 88}]},
    ]
}


def self_check():
    cases = []

    def add(state, name, got, want):
        cases.append((state, name, got, want))

    gaokao = {"final": 86, "finalW": 60,
              "comps": [{"name": "出勤", "weight": 20, "score": 95},
                        {"name": "作业", "weight": 30, "score": 88},
                        {"name": "期末小测", "weight": 50, "score": 84}]}
    add("正常", "平时分 = (95×20+88×30+84×50)÷100", part_score(gaokao), 87.4)
    add("正常", "课程成绩 = 86×60% + 87.4×40%", course_score(gaokao), 86.6)

    ratio = {"final": 80, "finalW": 50,
             "comps": [{"name": "A", "weight": 2, "score": 90},
                       {"name": "B", "weight": 3, "score": 80}]}
    add("正常", "权重 2:3 不凑 100，按比例折算", part_score(ratio), 84.0)
    add("正常", "课程成绩 = 80×50% + 84×50%", course_score(ratio), 82.0)

    add("边界", "缺期末分 → 课程成绩待填", course_score(
        {"finalW": 60, "comps": [{"name": "x", "weight": 1, "score": 90}]}), None)
    add("边界", "没有平时条目 → 待填", course_score(
        {"final": 90, "finalW": 60, "comps": []}), None)
    add("边界", "条目权重全 0 → 待填", course_score(
        {"final": 90, "finalW": 60, "comps": [{"name": "x", "weight": 0, "score": 90}]}), None)
    add("边界", "条目没填得分 → 该条不计，只剩一条照算", part_score(
        {"comps": [{"name": "a", "weight": 10, "score": ""},
                   {"name": "b", "weight": 10, "score": 80}]}), 80.0)
    add("边界", "期末权重 150 → 夹到 100", course_score(
        {"final": 80, "finalW": 150, "comps": [{"name": "x", "weight": 1, "score": 100}]}), 80.0)
    add("边界", "期末权重 -20 → 夹到 0（全看平时）", course_score(
        {"final": 80, "finalW": -20, "comps": [{"name": "x", "weight": 1, "score": 90}]}), 90.0)
    add("边界", "分数写成字符串（\"88\"）照算", course_score(
        {"final": "88", "finalW": 50, "comps": [{"name": "x", "weight": 1, "score": "90"}]}), 89.0)
    add("边界", "空课程表 → 加权平均算不出", weighted([])["avg"], None)
    add("边界", "学分 0 的课不计入加权",
        weighted([{"name": "x", "credit": 0, "final": 90, "finalW": 60,
                   "comps": [{"name": "a", "weight": 1, "score": 90}]}])["avg"], None)

    w = weighted(DEMO["courses"])
    add("正常", "演示 4 门课加权平均（与界面 89.1 同源）", w["avg"], 89.1)
    add("正常", "演示计入学分 = 5+4+4+1", w["credit"], 14.0)
    add("正常", "只看第 1 学期（高数+大英）", weighted(DEMO["courses"], 1)["avg"], 88.2)
    add("正常", "第 1 学期计入学分 = 9", weighted(DEMO["courses"], 1)["credit"], 9.0)
    add("正常", "分学期表有 2 行", len(term_table(DEMO["courses"])), 2)

    # 数据完整性：常量与口径不能悄悄变
    add("完整性", "默认期末权重 60%", DEFAULT_FINAL_W, 60)
    add("完整性", "学期→年级映射覆盖 1-8", sorted(CROSS_TERM_TO_GRADE.keys()),
        [1, 2, 3, 4, 5, 6, 7, 8])
    add("完整性", "公式文案含「Σ课程学分」", "Σ课程学分" in FORMULA, True)
    add("完整性", "GPA 不在默认输出里换算（还是「待学校换算规则」文案）",
        "待学校换算规则" in report(DEMO["courses"]), True)
    one = [{"name": "x", "credit": 3, "final": 80, "finalW": 50,
            "comps": [{"name": "a", "weight": 1, "score": 90}]}]
    add("正常", "示例 GPA：单门课程成绩 85、3 学分 → 3.50", sample_gpa(one), 3.5)
    low = [{"name": "y", "credit": 2, "final": 55, "finalW": 100,
            "comps": [{"name": "a", "weight": 1, "score": 0}]}]
    add("正常", "示例 GPA：课程成绩 55（<60）→ 计 0", sample_gpa(low), 0.0)
    add("完整性", "示例规则文案带「示例」标注", "示例" in SAMPLE_RULE_TEXT, True)

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
    args = sys.argv[1:]
    if args and args[0] == "--self-check":
        sys.exit(0 if self_check() else 1)
    term = None
    if "--term" in args:
        i = args.index("--term")
        if i + 1 >= len(args):
            print("--term 后面要跟学期号，如 --term 3")
            return
        try:
            term = int(args[i + 1])
        except ValueError:
            print("--term 要数字（1-8），收到的是 %r" % args[i + 1])
            return
        args = args[:i] + args[i + 2:]
    if args and args[0] == "--demo":
        data = DEMO
    elif args:
        try:
            with open(args[0], encoding="utf-8") as f:
                data = json.load(f)
        except OSError as e:
            print("读不到输入文件：%s（%s）" % (args[0], e.strerror or e))
            return
        except ValueError as e:
            print("输入文件不是合法 JSON：%s（%s）" % (args[0], e))
            return
    else:
        print(__doc__)
        return

    rule = None
    if "--rule" in args:
        i = args.index("--rule")
        if i + 1 >= len(args) or args[i + 1] != "sample":
            print("--rule 目前只支持 sample（内置示例规则）")
            return
        rule = "sample"
        args = args[:i] + args[i + 2:]
    courses = data.get("courses")
    if not isinstance(courses, list):
        print("courses 格式不对：要一个列表，每项是一门课"
              "（当前是 %s）" % type(courses).__name__)
        return
    print(report(courses, term, rule))


if __name__ == "__main__":
    main()
