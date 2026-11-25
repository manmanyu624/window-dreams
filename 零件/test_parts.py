#!/usr/bin/env python3
"""零件的测试：python3 test_parts.py，有一条不过就非零退出。
不调任何模型，不碰钥匙串（上锁那几条用临时的钥匙文件），文字全是编的。"""
import os, random, sys, tempfile
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

N = [0, 0]
def ok(cond, name):
    N[0] += 1
    if cond: N[1] += 1
    else: print("没过：", name)

# ---------- 一、上锁 ----------
td = tempfile.mkdtemp()
os.environ.pop("DREAM_KEY", None); os.environ["DREAM_KEY_FILE"] = str(Path(td) / "key")
import lock
a = lock.seal("桥下面的水是灰蓝色的。")
ok(lock.open_(a) == "桥下面的水是灰蓝色的。", "封了再开，一字不差")
ok("灰蓝" not in a and "桥" not in a, "密文里没有原文")
ok(lock.seal("桥下面的水是灰蓝色的。") != a, "同一句封两次，密文不一样（带盐）")
ok((Path(td) / "key").exists() and oct((Path(td) / "key").stat().st_mode)[-3:] == "600", "钥匙文件头一回自己生成，只有自己能读")
k1 = (Path(td) / "key").read_text()
lock.seal("再封一句"); ok((Path(td) / "key").read_text() == k1, "第二回用的是同一把，不重新生成")
os.environ["DREAM_KEY"] = "另一把钥匙"
try: lock.open_(a); ok(False, "换了钥匙应该开不了")
except Exception: ok(True, "换了钥匙开不了")
b = lock.seal("环境变量那把封的"); ok(lock.open_(b) == "环境变量那把封的", "环境变量给的钥匙排在文件前面，能封能开")
os.environ.pop("DREAM_KEY")
ok(lock.open_(a) == "桥下面的水是灰蓝色的。", "拿回原来那把，还开得了")

# ---------- 二、早上那副牌 ----------
import wake
for g, row in wake.SLOPE:
    ok(sum(row) == 100, f"{g} 分那行加起来 100")
    ok([round(x, 6) for x in wake.odds(g)] == list(row), f"{g} 分正好落在表上")
for g in range(0, 900, 7):
    o = wake.odds(g)
    ok(abs(sum(o) - 100) < 1e-9 and min(o) >= 0, f"{g} 分：和 100、没有负数")
ok(wake.odds(0) == wake.odds(30), "表头以内同一副")
ok(wake.odds(421) == wake.odds(2000), "表尾以外同一副")
ok(wake.odds(90) == [35, 53.5, 5.5, 6], "一个半小时落在两点正中")
s = [wake.odds(g) for g in range(30, 421, 5)]
ok(all(x[0] >= y[0] - 1e-9 for x, y in zip(s, s[1:])), "隔得越久，全记得只降不升")
ok(all(x[2] <= y[2] + 1e-9 for x, y in zip(s, s[1:])), "隔得越久，一句只升不降")
rng = random.Random(7)
for gap, want in ((10, [75, 22, 0, 3]), (180, [15, 62, 13, 10]), (500, [0, 20, 70, 10])):
    c = Counter(); R = 6000; bad = 0
    for _ in range(R):
        tier, give = wake.wake(40, gap, rng); c[tier] += 1
        if tier == "all" and len(give) != 40: bad += 1
        if tier == "one" and len(give) != 1: bad += 1
        if tier == "none" and give: bad += 1
        if tier == "most" and not (15 <= len(give) <= 28): bad += 1
        if any(i < 0 or i >= 40 for i in give): bad += 1
    ok(bad == 0, f"隔 {gap} 分：每档给的句数都对")
    for t, w in zip(wake.TIERS, want):
        ok(abs(c[t] / R * 100 - w) < 3, f"隔 {gap} 分抽 {R} 次：{t} 约 {w}%（实际 {c[t] / R * 100:.1f}）")
ok(wake.wake(1, 60, rng)[1] <= {0}, "只有一句的梦也不出错")

# ---------- 三、影子的把关 ----------
import shadow
FAKE = ("我站在一座很长的木桥上，桥下面的水是灰蓝色的。有人在对岸喊我的名字，声音却像从水底下传上来的。"
        "我低头看手里，握着一把生了锈的铜钥匙。桥板一块一块地往后退，我怎么走都走不到头。")
good = "颜色：灰蓝色\n感觉：走不到头的慌\n物件：一件开门的旧东西"
ok(shadow.parse_and_check(good, FAKE) == {"color": "灰蓝色", "feel": "走不到头的慌", "thing": "一件开门的旧东西"}, "规规矩矩的三行：过")
ok(shadow.parse_and_check("1. **颜色**: 灰蓝色\n- 感觉：「走不到头的慌」\n\n物件：一件开门的旧东西", FAKE) is not None, "带编号、加粗、引号、半角冒号、空行：也认")
ok(shadow.parse("颜色：灰蓝色\n感觉：慌") is None, "缺一样：不认")
ok(shadow.parse("颜色：灰蓝\n颜色：白\n感觉：慌\n物件：一个东西") is None, "同一样出现两次：不认")
ok(shadow.parse_and_check("颜色：灰蓝色\n感觉：走不到头的慌\n物件：一把生锈的铜钥匙", FAKE) is None, "物件直接说出了名字：不过")
ok(shadow.check_one("thing", "一把钥匙", FAKE) is None, "物件带了原文里的两个字（钥匙）：不过")
ok(shadow.check_one("thing", "一件开门的旧东西", FAKE) == "一件开门的旧东西", "物件只说大概：过")
ok(shadow.check_one("feel", "我怎么走都走不到头，很慌。", FAKE) is None, "感觉写成了句子：不过")
ok(shadow.check_one("color", "灰", FAKE) is None and shadow.check_one("color", "很深很深很深的灰蓝色", FAKE) is None, "颜色太短、太长：不过")
ok(shadow.check_one("feel", "桥板一块一块地往后退", FAKE) is None, "照抄原文一长串：不过")
asked = []
def fake_ask(text, temperature=0.3, avoid=None):
    asked.append((temperature, avoid))
    return ["颜色：灰蓝色\n感觉：走不到头的慌\n物件：一把铜钥匙", good][min(len(asked) - 1, 1)]
shadow._ask = fake_ask
ok(shadow.make_shadow(FAKE) == {"color": "灰蓝色", "feel": "走不到头的慌", "thing": "一件开门的旧东西"}, "第一次物件说破了，重问一次就过")
ok(len(asked) == 2 and asked[1][0] > asked[0][0] and asked[1][1] == "一把铜钥匙", "重问时温度调高，并点名上次那个物件别再写")
asked.clear(); shadow._ask = lambda text, temperature=0.3, avoid=None: "颜色：灰蓝色\n感觉：走不到头的慌\n物件：一把铜钥匙"
ok(shadow.make_shadow(FAKE) == {"color": "灰蓝色", "feel": "走不到头的慌", "thing": ""}, "问三次物件都说破：只留颜色和感觉，物件空着")
shadow._ask = lambda text, temperature=0.3, avoid=None: "我觉得这段文字很美。"
ok(shadow.make_shadow(FAKE) is None, "三次都答非所问：什么都不留")
ok(shadow.make_shadow("   ") is None, "空的不问")

# ---------- 四、打碎之后的收拾、像不像 ----------
import shatter, embed
ok(shatter.clean("1. 灰蓝的水\n- 六十六颗\n\n这一行实在是太长了太长了太长了太长了太长了太长了\n桥\n· 往后退的桥板", 12) == ["灰蓝的水", "六十六颗", "往后退的桥板"], "碎片：去编号、去太长太短的")
ok(len(shatter.clean("\n".join(f"碎片{i}" for i in range(30)), 12)) == 12, "碎片：最多留 n 片")
ok(abs(embed.cos([1, 0], [1, 0]) - 1) < 1e-6 and abs(embed.cos([1, 0], [0, 1])) < 1e-6 and abs(embed.cos([1, 0], [-1, 0]) + 1) < 1e-6, "像不像：同向 1、垂直 0、反向 -1")

print(f"共 {N[0]} 条，过 {N[1]} 条，没过 {N[0] - N[1]} 条。")
sys.exit(0 if N[0] == N[1] else 1)
