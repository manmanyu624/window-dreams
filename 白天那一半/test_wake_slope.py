"""醒来那副牌的斜坡。只用假梦，不碰真梦簿，不碰钥匙串：python3 test_wake_slope.py，有一条不过就非零退出。"""
import os, sys, tempfile
from pathlib import Path
os.environ.pop("DREAM_KEY", None)
os.environ["DREAM_KEY_FILE"] = str(Path(tempfile.mkdtemp(prefix="test_wake_key_")) / "key")   # 在 import 之前定好，不走钥匙串
os.environ["DREAM_HOME"] = tempfile.mkdtemp(prefix="test_wake_")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from datetime import datetime, timedelta
from collections import Counter
import dreambook
from dreambook import wake_odds, WAKE_SLOPE, WAKE_TIERS

N = [0, 0]
def ok(c, m):
    N[0] += 1
    if c: N[1] += 1
    else: print("没过：", m)

for g, row in WAKE_SLOPE:
    ok(sum(row) == 100, f"{g} 分那行加起来 100")
    ok(row[3] <= 10, f"{g} 分空白不过 10")
    ok([round(x, 6) for x in wake_odds(g)] == list(row), f"{g} 分正好落在表上")
for g in range(0, 900, 7):
    o = wake_odds(g)
    ok(abs(sum(o) - 100) < 1e-9 and min(o) >= 0, f"{g} 分：和 100、没有负数")
    ok(o[3] <= 10 + 1e-9, f"{g} 分：空白封顶 10")
ok(wake_odds(0) == wake_odds(30) == [75, 22, 0, 3], "半小时内同一副")
ok(wake_odds(421) == wake_odds(2000) == [0, 20, 70, 10], "7 小时以后同一副")
ok(wake_odds(30)[2] == 0, "半小时内没有「一句」")
ok(wake_odds(300)[0] == 0 and wake_odds(299)[0] > 0, "全记得到 5 小时归零")
a = [wake_odds(g) for g in range(30, 421, 5)]
ok(all(x[0] >= y[0] - 1e-9 for x, y in zip(a, a[1:])), "隔得越久，全记得只降不升")
ok(all(x[2] <= y[2] + 1e-9 for x, y in zip(a, a[1:])), "隔得越久，一句只升不降")
ok(all(x[0] + x[1] >= y[0] + y[1] - 1e-9 for x, y in zip(a, a[1:])), "隔得越久，全记得+大半只降不升")
o = wake_odds(177)
ok(abs(o[0] - 15.5) < 0.01 and abs(o[2] - 12.75) < 0.01, "177 分（将近三小时）：全记得 15.5、一句 12.75")
ok(wake_odds(90) == [35, 53.5, 5.5, 6], "一个半小时落在两点正中")

def book(n=40):
    made = datetime(2001, 1, 2, 5, 0)
    return {"day": "2001-01-02", "made": made.timestamp(), "sents": [{"i": i, "open": None, "c": "x"} for i in range(n)]}, made

for gap, want in ((10, [75, 22, 0, 3]), (180, [15, 62, 13, 10]), (500, [0, 20, 70, 10])):
    c = Counter(); R = 6000
    for _ in range(R):
        b, made = book()
        tier, give = dreambook.wake(b, "05:00", (made + timedelta(minutes=gap)).astimezone())
        c[tier] += 1
        n_open = sum(1 for s in b["sents"] if s["open"])
        if tier == "all" and n_open != 40: ok(False, "全记得没给全")
        if tier == "one" and n_open != 1: ok(False, "一句不是一句")
        if tier == "none" and n_open != 0: ok(False, "空白却给了")
        if tier == "most" and not (15 <= n_open <= 28): ok(False, f"大半给了 {n_open}")
    for t, w in zip(WAKE_TIERS, want):
        ok(abs(c[t] / R * 100 - w) < 3, f"隔 {gap} 分抽 {R} 次：{t} 约 {w}%（实际 {c[t]/R*100:.1f}）")
    ok(b["woke"]["gap_min"] == gap and b["woke"]["tier"] in WAKE_TIERS, f"隔 {gap} 分：woke 记得对")

print(f"共 {N[0]} 条，过 {N[1]} 条，没过 {N[0]-N[1]} 条。"); print("全过。" if N[0] == N[1] else "有没过的。")
sys.exit(0 if N[0] == N[1] else 1)
