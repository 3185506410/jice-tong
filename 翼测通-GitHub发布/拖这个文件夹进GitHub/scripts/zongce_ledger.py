# -*- coding: utf-8 -*-
"""综测核算 · 六块分数 + 性价比排序 + 本学期可挣的分

只做加权求和与差额计算，不做任何推测。
每个常量都标注了原文出处，可逐条回查。

用法：
    python zongce_ledger.py --demo                  # 内置样例
    python zongce_ledger.py zongce.json            # 读学生填的分

zongce.json 格式（学生填或模型抽取后写入）：
{
  "scores": {"de": 90, "zhi": 85, "ti": 70, "mei": 60, "lao": 65, "xs": 8},
  "deduct": {"警告处分": 1}
}
"""
import json
import sys

# ============================================================
# 六块定义 —— 全部来自《人工智能学院本科生综合素质测评实施细则》
#            （2025年10月修订版）第五条
#
# 综测成绩 = 德育×10% + 智育×70% + 体育×10% + 美育×5% + 劳动教育×5%
#            + 学术科技与创新创业实践 − 扣分
#
# 注意：学术科技与创新创业是「单设」项，不进权重、直连总分、上限20分。
#       这是唯一「挣1分算1分」的板块，其余五块挣1分总分只涨0.05~0.7。
# ============================================================
BLOCKS = [
    {"key": "de",  "name": "德育", "weight": 0.10, "cap": 100,
     "src": "细则第五条、第六条（一）"},
    {"key": "zhi", "name": "智育", "weight": 0.70, "cap": 100,
     "src": "细则第六条（二）：所修课程加权平均分，不含再修/辅修/微专业"},
    {"key": "ti",  "name": "体育", "weight": 0.10, "cap": 100,
     "src": "细则第六条（三）：体测 + 阳光体育打卡"},
    {"key": "mei", "name": "美育", "weight": 0.05, "cap": 100,
     "src": "细则第六条（四）"},
    {"key": "lao", "name": "劳动教育", "weight": 0.05, "cap": 100,
     "src": "细则第六条（五）"},
    {"key": "xs",  "name": "学术科技与创新创业", "weight": None, "cap": 20,
     "src": "细则第五条（单设）、第六条加分条款：上限20分，直接计入总分"},
]

# 扣分项 —— 细则第六条原文
DEDUCTIONS = {
    "留校察看处分": 10,
    "记过处分": 8,
    "严重警告处分": 6,
    "警告处分": 4,
    "通报批评": 2,
}

# 学科竞赛加分六级 —— 细则第六条原文照抄
COMP = [
    ("国甲类",          20,   16,   12,  2),
    ("国乙类",          15,   12,    9,  1.5),
    ("国丙类/省甲类",   10,    8,    6,  1),
    ("省乙类",           8,  6.4,  4.8,  0.8),
    ("校级",             5,    4,    3,  0.5),
    ("院级",             3,  2.4,  1.8,  0.3),
]

CAP_NOTE = "细则第十四条：同一事项加减分按就高不就低；第十五条：加分须以学校为第一单位"


def norm_num(v):
    """把学生填的值转成数字。填不出来就返回 None，不猜。"""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute(scores, deduct=None):
    """算总分、五育小计、附加分、扣分。算不出来的板块返回 None。"""
    base = 0.0
    extra = 0.0
    missing = []
    rows = []
    for b in BLOCKS:
        g = norm_num(scores.get(b["key"]))
        if g is None:
            missing.append(b["name"])
            rows.append(dict(b, got=None, contrib=0.0, remain=b["cap"]))
            continue
        if b["weight"] is None:
            contrib = g
            extra = g
        else:
            contrib = g * b["weight"]
            base += contrib
        rows.append(dict(b, got=g, contrib=contrib, remain=max(0.0, b["cap"] - g)))

    ded_total = 0.0
    ded_detail = []
    for name, times in (deduct or {}).items():
        t = norm_num(times) or 0
        if t == 0:
            continue
        per = DEDUCTIONS.get(name)
        if per is None:
            continue
        amt = per * t
        ded_total += amt
        ded_detail.append((name, t, per, amt))

    total = base + extra - ded_total
    return dict(base=base, extra=extra, deduct=ded_total,
                total=total, rows=rows, missing=missing,
                ded_detail=ded_detail)


def advise(res):
    """按「缺口 × 效率」排建议。只用规则内的量，不猜。"""
    out = []
    xs = [r for r in res["rows"] if r["key"] == "xs"][0]
    if xs["got"] is None or xs["got"] < xs["cap"]:
        gap = xs["cap"] - (xs["got"] or 0)
        out.append((
            "★ 优先：学术科技与创新创业",
            "还差 %.1f 分封顶。它不乘权重，挣 1 分总分就涨 1 分；"
            "其余五块挣 1 分，总分只涨 0.05~0.7。依据：细则第五条（单设项）。" % gap))

    # 缺口×效率排序（排除直连块，避免与上一条重复）
    rest = []
    for r in res["rows"]:
        if r["weight"] is None or r["got"] is None:
            continue
        gap = r["cap"] - r["got"]
        if gap <= 0.5:
            continue
        rest.append((gap * r["weight"], r))
    rest.sort(key=lambda x: -x[0])
    for gain, r in rest[:2]:
        out.append((
            "其次：%s" % r["name"],
            "还差 %.1f 分；这块权重 %d%%，补满最多给总分加 %.1f 分。"
            "（%s）" % (r["remain"], round(r["weight"] * 100), gain, r["src"])))

    toped = [r["name"] for r in res["rows"]
             if r["got"] is not None and r["got"] >= r["cap"] - 0.01]
    if toped:
        out.append(("已到顶：" + "、".join(toped),
                    "这块再加也不涨总分了，把时间挪到上面两项。"))

    if res["deduct"] > 0:
        out.append(("⚠ 你有在计的扣分项",
                    "扣分直接从总分里扣。细则第六条：留校察看10、记过8、"
                    "严重警告6、警告4、通报批评2。先处理扣分，"
                    "收益比多参加一个比赛大。"))

    if not out:
        out.append(("先填一块，我再告诉你往哪投入", ""))
    return out


def report(res, res_adv):
    L = []
    L.append("# 综测核算结果\n")
    L.append("## 一、总分\n")
    L.append("| 构成 | 数值 |")
    L.append("|---|---|")
    L.append("| 五育加权小计 | %.1f |" % res["base"])
    L.append("| 学术科技附加（直连总分） | %.1f |" % res["extra"])
    if res["deduct"] > 0:
        L.append("| 扣分 | -%.1f |" % res["deduct"])
    L.append("| **综测总分** | **%.1f** |" % res["total"])
    L.append("")
    L.append("> 计算依据：细则第五条 "
             "`综测成绩 = 德育×10% + 智育×70% + 体育×10% + 美育×5% "
             "+ 劳动教育×5% + 学术科技与创新创业实践 − 扣分`")
    L.append("")

    L.append("## 二、六块明细\n")
    L.append("| 板块 | 权重 | 已得 | 折算进总分 | 上限 | 还差 | 依据 |")
    L.append("|---|---|---|---|---|---|---|")
    for r in res["rows"]:
        w = "直连" if r["weight"] is None else "%d%%" % round(r["weight"] * 100)
        got = "—" if r["got"] is None else "%.1f" % r["got"]
        L.append("| %s | %s | %s | %s | %d | %.1f | %s |"
                 % (r["name"], w, got,
                    "—" if r["got"] is None else "%.2f" % r["contrib"],
                    r["cap"], r["remain"], r["src"]))
    L.append("")

    sec = 3
    cn = {3: "三", 4: "四", 5: "五", 6: "六"}
    if res["missing"]:
        L.append("## %s、需要你补的（系统不推测）\n" % cn[sec])
        for m in res["missing"]:
            L.append("- %s：没填分数，**不填 0、不猜、不计入**。" % m)
        L.append("")
        L.append("> 没填的板块按「不算」处理，所以当前总分是**不完整**的。")
        L.append("")
        sec += 1

    if res["ded_detail"]:
        L.append("## %s、扣分明细（细则第六条）\n" % cn[sec])
        L.append("| 情形 | 次数 | 每次 | 小计 |")
        L.append("|---|---|---|---|")
        for name, t, per, amt in res["ded_detail"]:
            L.append("| %s | %g | -%d | -%.1f |" % (name, t, per, amt))
        L.append("")
        sec += 1

    L.append("## %s、该往哪块投入\n" % cn[sec])
    for title, desc in res_adv:
        L.append("### %s" % title)
        if desc:
            L.append(desc)
        L.append("")
    sec += 1

    L.append("## %s、学科竞赛加分表（细则第六条原文）\n" % cn[sec])
    L.append("| 竞赛级别 | 最高奖/第一名 | 次高奖/第2-3名 | 再次高奖/第4-8名 | 成功参赛/优胜 |")
    L.append("|---|---|---|---|---|")
    for row in COMP:
        L.append("| %s | %g | %g | %g | %g |" % row)
    L.append("")
    L.append("**六条隐藏约束**（决定「该不该报」）：")
    L.append("")
    L.append("1. 队内排名折算（学科竞赛）：`个人加分 = 奖项对应分值 ÷ [1+(排序−1)×0.5]`，"
             "第1名100%、第2名66.7%、第3名50%、第4名40%……")
    L.append("2. 同一个获奖认定人数**不超过 8 人**，按获奖证书排序取前 8")
    L.append("3. ⚠ **论文的作者权重是另一套**：第二作者 0.5、第三作者 0.3、"
             "第四作者起不加分（细则第六条（一）注①）——只用于学术论文，"
             "**别套到学科竞赛上**")
    L.append("4. 必须以学校为第一单位参与，写在别的单位下的成果一分不算")
    L.append("5. 同一个竞赛取最高分计入，不重复加分")
    L.append("6. %s" % CAP_NOTE)
    L.append("")
    L.append("---")
    L.append("**不做的事**：不猜获奖概率（没有往年数据）、不替你决定报不报、"
             "不把系统判断不了的当成结论。官方认定权在学院与教务处。")
    return "\n".join(L)


DEMO = {
    "scores": {"de": 90, "zhi": 85, "ti": 70, "mei": 60, "lao": 65, "xs": 8},
    "deduct": {"警告处分": 1},
}


def self_check():
    """三态自检：正常 / 边界 / 数据完整性。打印 N/N，任一不过即非 0 退出。"""
    cases = []

    def chk(state, name, got, want):
        cases.append((state, name, got, want))

    # ---- 正常：已知公式的用例 ----
    demo = compute(DEMO["scores"], DEMO["deduct"])
    chk("正常", "样例五育加权小计 = 81.75", demo["base"], 81.75)
    chk("正常", "样例学术科技附加 = 8（直连总分）", demo["extra"], 8)
    chk("正常", "样例扣分 = 4（警告处分 1 次）", demo["deduct"], 4)
    chk("正常", "样例总分 = 81.75+8-4 = 85.75", demo["total"], 85.75)
    chk("正常", "只填学术科技 20 分 → 总分 20", compute({"xs": 20})["total"], 20)
    chk("正常", "记过 2 次 = 扣 16", compute({}, {"记过处分": 2})["deduct"], 16)
    chk("正常", "通报批评 1 次 = 扣 2", compute({}, {"通报批评": 1})["deduct"], 2)
    chk("正常", "智育 85 × 0.7 折进总分 59.5",
        round([r for r in compute({"zhi": 85})["rows"] if r["key"] == "zhi"][0]["contrib"], 2), 59.5)
    chk("正常", "学术科技不乘权重，挣 1 分涨 1 分",
        [r for r in compute({"xs": 8})["rows"] if r["key"] == "xs"][0]["contrib"], 8)
    chk("正常", "报告含总分行", "综测总分" in report(demo, advise(demo)), True)

    # ---- 边界：必须「不知道」，不许编 ----
    chk("边界", "空成绩单 → 六块全进 missing",
        len(compute({})["missing"]), 6)
    chk("边界", "空成绩单 → 总分 0 且不猜", compute({})["total"], 0)
    chk("边界", "norm_num('') → None", norm_num(""), None)
    chk("边界", "norm_num(None) → None", norm_num(None), None)
    chk("边界", "norm_num('abc') → None（不猜）", norm_num("abc"), None)
    chk("边界", "未知扣分项不计入", compute({}, {"不存在的处分": 1})["deduct"], 0)
    chk("边界", "扣分 0 次不计入明细",
        compute({}, {"警告处分": 0})["ded_detail"], [])
    chk("边界", "超过上限时 remain 归 0",
        [r for r in compute({"zhi": 120})["rows"] if r["key"] == "zhi"][0]["remain"], 0)

    # ---- 数据完整性：常量表与原文一致性的硬断言 ----
    chk("完整", "六块齐全", len(BLOCKS), 6)
    chk("完整", "前五块权重合计 = 1.0（细则第五条）",
        round(sum(b["weight"] for b in BLOCKS if b["weight"]), 10), 1.0)
    chk("完整", "学术科技是唯一 weight=None 的单设项",
        [b["key"] for b in BLOCKS if b["weight"] is None], ["xs"])
    chk("完整", "学术科技封顶 = 20（细则第五条）",
        [b["cap"] for b in BLOCKS if b["key"] == "xs"][0], 20)
    chk("完整", "其余五块满分 = 100",
        sorted(b["cap"] for b in BLOCKS if b["weight"] is not None), [100] * 5)
    chk("完整", "扣分表 = 留校察看10/记过8/严重警告6/警告4/通报批评2",
        DEDUCTIONS, {"留校察看处分": 10, "记过处分": 8, "严重警告处分": 6,
                     "警告处分": 4, "通报批评": 2})
    chk("完整", "综测竞赛加分六级齐全", len(COMP), 6)
    chk("完整", "国甲类一等奖 = 20（细则第六条原文）", COMP[0][1], 20)
    chk("完整", "省甲类一等奖 = 10（细则第六条原文）", COMP[2][1], 10)
    chk("完整", "建议首条指向学术科技（未满时性价比最高）",
        advise(compute(DEMO["scores"]))[0][0].startswith("★ 优先"), True)

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

    if data.get("deduct") is not None and not isinstance(data.get("deduct"), dict):
        print("deduct 格式不对：要 {\"处分名\": 次数}，如 {\"警告处分\": 1}"
              "（当前是 %s）" % type(data.get("deduct")).__name__)
        return

    res = compute(data.get("scores", {}), data.get("deduct"))
    print(report(res, advise(res)))


if __name__ == "__main__":
    main()
