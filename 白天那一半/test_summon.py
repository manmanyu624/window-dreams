#!/usr/bin/env python3
"""「她唤的」、钩子整轮、梦簿锁的测试。纯 Python：python3 test_summon.py，有一条不过就非零退出。
不调模型（embed.embed 换成假的），不碰真的梦：DREAM_HOME 指到临时目录，梦全是编的。
上锁用临时的钥匙文件（DREAM_KEY_FILE），不碰钥匙串；要有系统自带的 openssl。"""
import io, json, os, shutil, subprocess, sys, tempfile, time
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="test_summon_"))
KEYDIR = Path(tempfile.mkdtemp(prefix="test_summon_key_"))
os.environ.pop("DREAM_KEY", None)
os.environ["DREAM_KEY_FILE"] = str(KEYDIR / "key")   # 钥匙走临时文件，不走钥匙串；必须在 import 之前定好
os.environ["DREAM_HOME"] = str(TMP)            # 必须在 import dreambook 之前定好
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "零件"))
import dreambook, embed, hook_before, hook_after, summon
dlock = dreambook.dlock

assert dreambook.BOOK == TMP / "梦簿", "梦簿没指到临时目录，停"
dreambook.BOOK.mkdir()

FAILS, N = [], 0
def ok(cond, name):
    global N
    N += 1
    print(("  过  " if cond else "  没过 ") + name)
    if not cond: FAILS.append(name)

embed.embed = lambda texts: [[0.1, 0.2, 0.3] for _ in texts]      # 假向量：所有句子意思一样，意思那条路永远甩不开，只有字面能开
assert dlock.open_(dlock.seal("试一下")) == "试一下", "上锁用不了（要有 openssl），停"

# 编的假梦（六句）
S = ["我在一间没有窗户的面包店里排队。", "柜台后面的人一直在数硬币，数了很久。", "轮到我的时候，货架上只剩一只橘子味的蛋糕。",
     "我抱着蛋糕走出门，外面忽然变成了雪地。", "远处有一列绿皮火车慢慢开过去。", "我想追上去，鞋子却陷在雪里拔不出来。"]
C = [dlock.seal(t) for t in S]                 # 封一次反复用
SQ, Q = TMP / "summoned.json", TMP / "queued.json"
QUIET = "嗯嗯"                                  # 梦里没有的字：她这句什么都勾不开

def clean():
    for f in dreambook.BOOK.glob("*"): f.unlink()
    for f in (SQ, Q):
        if f.is_dir(): f.rmdir()
        elif f.exists(): f.unlink()
def book(opened=(), woke=True, told=False, pending=False, how="醒来"):
    """摆一本今天的假梦簿到临时目录：opened 里的句子按 how 开着。回 (路径, 梦簿)。"""
    clean()
    now = time.time()
    b = {"day": date.today().isoformat(), "made": now - 3 * 3600, "made_hm": "05:20", "guesses": 0, "src": dlock.seal("{}"),
         "sents": [{"i": i, "c": C[i], "v": [0.1, 0.2, 0.3], "open": ({"t": now - 2 * 3600, "how": how} if i in opened else None)} for i in range(len(S))]}
    if woke: b["woke"] = {"at": datetime.now().astimezone().isoformat(), "tier": "most", "gap_min": 200}
    if told: b["told_all"] = now
    if pending: b["pending_morning"] = True
    p = dreambook.BOOK / f"{b['day']}.json"; dreambook._save(p, b)
    return p, b
def disk(p): return json.loads(p.read_text())
def how_of(p, i): return ((disk(p)["sents"][i]).get("open") or {}).get("how")

# ---------- 一、dreambook.summon ----------
print("一、dreambook.summon / summon_why")
_, b = book(woke=False);          ok(dreambook.summon(b, 1) is None and dreambook.summon_why(b, 1) == "还没醒" and dreambook.summon(b) is None, "没醒：不开，原因「还没醒」")
_, b = book({0}, pending=True)
ok(dreambook.summon(b, 1) is None and dreambook.summon(b) is None and dreambook.summon_why(b, 1) == "还没醒" and dreambook.summon_why(b) == "还没醒"
   and all(s["open"] is None for s in b["sents"][1:]), "醒了但晨递还没递出去（pending_morning）：不开，原因「还没醒」")
b["pending_morning"] = False
ok(dreambook.summon_why(b, 1) is None and dreambook.summon(b, 1) == (1, S[1]), "pending_morning 变 False 之后：能唤")
_, b = book({0}, told=True);      ok(dreambook.summon(b, 1) is None and dreambook.summon_why(b) == "已经讲完了", "讲完了：不开，原因「已经讲完了」")
_, b = book({0})
ok(all(dreambook.summon(b, x) is None and dreambook.summon_why(b, x) == "编号不对" for x in (-1, 6, 99, "2", 1.0, True)), "编号越界 / 不是整数：不开，原因「编号不对」")
ok(dreambook.summon(b, 0) is None and dreambook.summon_why(b, 0) == "这句已经想起来了", "那句已经开了：不开，原因「这句已经想起来了」")
_, b = book(range(6));            ok(dreambook.summon(b) is None and dreambook.summon_why(b) == "没有可唤的了", "全开了：不开，原因「没有可唤的了」")
ok(not hasattr(dreambook, "SUMMON_CAP"), "不设上限：没有 SUMMON_CAP")
p, b = book({0})
r = dreambook.summon(b, 4)
ok(r == (4, S[4]), "给 i：回 (i, 明文)")
ok(b["sents"][4]["open"]["how"] == "她唤的" and isinstance(b["sents"][4]["open"]["t"], float) and set(b["sents"][4]["open"]) == {"t", "how"}, "开的方式：{t, how: 她唤的}")
ok(disk(p)["sents"][4]["open"] is None, "summon 不存盘")
ok(all(b["sents"][k]["open"] is None for k in (1, 2, 3, 5)), "别的句子没动")
seen = set()
for _ in range(40):
    _, b = book({2}); i, t = dreambook.summon(b); seen.add(i); assert t == S[i]
ok(seen <= {1, 3} and seen == {1, 3}, f"不给 i、有已开的：只挑挨着的（40 次挑到 {sorted(seen)}）")
seen = set()
for _ in range(40):
    _, b = book({0, 1, 2, 3}); i, t = dreambook.summon(b); seen.add(i)
ok(seen == {4}, "不给 i：已开 0~3，只有 4 挨着，一定挑 4")
seen = set()
for _ in range(60):
    _, b = book(()); i, t = dreambook.summon(b); seen.add(i); assert b["sents"][i]["open"]["how"] == "她唤的"
ok(len(seen) >= 3 and seen <= set(range(6)), f"不给 i、一句都没开（没有挨着的）：随机挑没开的（60 次挑到 {sorted(seen)}）")
_, b = book((1, 3, 5)); i, _t = dreambook.summon(b)
ok(i in (0, 2, 4), "不给 i：挑到的一定是没开的")
_, b = book(())
got = [dreambook.summon(b) for _ in range(6)]
ok(all(g is not None for g in got) and sorted(g[0] for g in got) == list(range(6)) and dreambook.summon(b) is None, "不设上限：能一句句唤到全开，之后「没有可唤的了」")
ok(all(abs(got[k][0] - got[k + 1][0]) >= 1 for k in range(5)) and all(
    any(abs(got[k + 1][0] - got[j][0]) == 1 for j in range(k + 1)) for k in range(5)), "连着不给 i 唤：第二句起每次都挨着已经唤开的")

# ---------- 二、summon.py 命令行 ----------
print("二、summon.py 命令行")
def cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf): summon.main(list(argv))
    return buf.getvalue()
def j(s): return json.loads(s)
OUTS = []
def run_cli(*argv):
    s = cli(*argv); OUTS.append(s); return s
clean()
s = run_cli();                       ok(j(s) == {"ok": False, "why": "没有梦"} and s.count("\n") == 1, "没有梦簿：{ok:false, why:没有梦}，只一行")
p, _ = book(woke=False);             ok(j(run_cli("--i", "1")) == {"ok": False, "why": "还没醒"} and how_of(p, 1) is None, "还没醒")
p, _ = book({0}, told=True);         ok(j(run_cli()) == {"ok": False, "why": "已经讲完了"} and not SQ.exists(), "已经讲完了：不排队")
p, _ = book({0})
ok(j(run_cli("--i", "0")) == {"ok": False, "why": "这句已经想起来了"}, "这句已经想起来了")
ok(all(j(run_cli(*a)) == {"ok": False, "why": "编号不对"} for a in (("--i", "99"), ("--i", "-1"), ("--i", "abc"), ("--i",), ("--x", "1"), ("--i", "1", "2"))), "编号不对（越界 / 不是数 / 缺值 / 别的参数）")
p, _ = book(range(6));               ok(j(run_cli()) == {"ok": False, "why": "没有可唤的了"}, "没有可唤的了")
p, _ = book({0})
s = run_cli("--i", "3")
ok(j(s) == {"ok": True, "i": 3} and s.count("\n") == 1, "成功：{ok:true, i:3}，没有 left，只一行")
ok(how_of(p, 3) == "她唤的", "成功：梦簿存了盘，第 3 句是「她唤的」")
s = run_cli("--i=5"); ok(j(s) == {"ok": True, "i": 5}, "--i=5 的写法也认")
s = run_cli(); r = j(s); ok(r["ok"] is True and r["i"] in (1, 2, 4) and set(r) == {"ok", "i"}, "不给 i：成功，挑的是挨着已开的")
q = json.loads(SQ.read_text())
ok(isinstance(q, list) and len(q) == 3 and [x["i"] for x in q] == [3, 5, r["i"]], "summoned.json 追加三次：三项，按唤的先后")
ok(all(set(x) == {"i", "at"} and isinstance(x["at"], float) for x in q), "每项只有 i 和 at")
p, _ = book({0}); run_cli("--i", "2"); run_cli("--i", "4")
q = json.loads(SQ.read_text())
ok([x["i"] for x in q] == [2, 4] and all(set(x) == {"i", "at"} for x in q), "追加两次：两项，只记编号")
ok(not (TMP / "summoned.json.tmp").exists(), "临时文件换过去了，没剩下")
ok(not any(t in SQ.read_text() for t in S) and not any(t[:4] in SQ.read_text() for t in S), "summoned.json 里没有明文")
# 上一个梦留下的项：追加时丢掉
p, b = book({0}); SQ.write_text(json.dumps([{"i": 1, "at": b["made"] - 100}])); run_cli("--i", "2")
ok([x["i"] for x in json.loads(SQ.read_text())] == [2], "summoned.json 里上一个梦的项：追加时丢掉")
p, b = book({0}); SQ.write_text("{坏的"); run_cli("--i", "2")
ok([x["i"] for x in json.loads(SQ.read_text())] == [2], "summoned.json 是坏的：重新起一个列表")
# 出错了：存盘时炸
def boom(*a, **k): raise RuntimeError("炸了 " + S[2])
p, _ = book({0}); _real_save = dreambook._save; dreambook._save = boom
s = run_cli("--i", "2"); dreambook._save = _real_save
ok(j(s) == {"ok": False, "why": "出错了"} and how_of(p, 2) is None and not SQ.exists(), "存盘时炸：{ok:false, why:出错了}，梦簿没动，没排队，异常里的字没打出来")
# 出错了：排队写不进去（summoned.json 被一个目录占着）→ 把那句关回去
p, _ = book({0}); SQ.mkdir()
s = run_cli("--i", "2")
ok(j(s) == {"ok": False, "why": "出错了"} and how_of(p, 2) is None, "排不进队：出错了，那句关回去了（不会开了却永远递不到）")
SQ.rmdir()
ok(not any(t in o or t[:4] in o for o in OUTS for t in S), f"以上 {len(OUTS)} 次输出里都没有句子的明文")
# 子进程：真的命令行跑，退出码一律 0
def sub(*argv):
    r = subprocess.run([sys.executable, str(HERE / "summon.py"), *argv], capture_output=True, text=True, env=dict(os.environ, DREAM_HOME=str(TMP)), cwd=str(HERE))
    return r.returncode, r.stdout, r.stderr
clean(); rc, o, e = sub()
ok(rc == 0 and j(o) == {"ok": False, "why": "没有梦"} and e == "", "子进程 没有梦：退出码 0，一行 json，stderr 空")
p, _ = book({0}); rc, o, e = sub("--i", "abc")
ok(rc == 0 and j(o) == {"ok": False, "why": "编号不对"}, "子进程 编号不对：退出码 0")
rc, o, e = sub("--i", "1")
ok(rc == 0 and j(o) == {"ok": True, "i": 1} and how_of(p, 1) == "她唤的" and not any(t[:4] in o + e for t in S), "子进程 成功：退出码 0，没有明文")
os.chmod(dreambook.BOOK, 0o500)                 # 梦簿目录只读：存盘会炸
rc, o, e = sub("--i", "2"); os.chmod(dreambook.BOOK, 0o700)
ok(rc == 0 and j(o) == {"ok": False, "why": "出错了"} and e == "", "子进程 存不了盘：出错了，退出码 0，stderr 空")

# ---------- 三、钩子整轮 ----------
print("三、钩子整轮（hook_before.main）")
def run_hook(prompt, mod=None):
    mod = mod or hook_before
    old_in = sys.stdin; sys.stdin = io.StringIO(json.dumps({"prompt": prompt})); buf = io.StringIO()
    try:
        with redirect_stdout(buf): mod.main()
    finally: sys.stdin = old_in
    s = buf.getvalue().strip()
    return json.loads(s)["hookSpecificOutput"]["additionalContext"] if s else None
ONE, MANY = hook_before.SUMMON_ONE, hook_before.SUMMON_MANY
ok(ONE == "（像有人在梦边上轻轻敲了一下，昨晚有一句浮上来了：『{}』）", "一句的文案：一字不差")
ok(MANY == "（像有人在梦边上轻轻敲了几下，昨晚有几句浮上来了：\n{}\n）", "几句的文案")
ok("她" not in ONE and "她" not in MANY, "文案里没有「她」字")

p, _ = book({0}); cli("--i", "3")
got = run_hook(QUIET)
ok(got == "（像有人在梦边上轻轻敲了一下，昨晚有一句浮上来了：『" + S[3] + "』）", "唤一句：下一轮递出单句文案，那句在里面")
ok(not SQ.exists(), "递完 summoned.json 删了")
ok(run_hook(QUIET) is None, "再下一轮不再递")

p, _ = book({0}); cli("--i", "4"); cli("--i", "1")
got = run_hook(QUIET)
ok(got == "（像有人在梦边上轻轻敲了几下，昨晚有几句浮上来了：\n「" + S[1] + "」\n「" + S[4] + "」\n）", "唤两句（先 4 后 1）：一次给，按梦里顺序 1、4")

p, _ = book({1, 2}); cli("--i", "3")
got = run_hook(QUIET)
ok(got == "（昨晚梦里的那一小段，又慢慢浮上来了：\n「" + S[1] + "」\n「" + S[2] + "」\n「" + S[3] + "」\n）", "唤的那句跟已开的连成段：走「连成段」的文案")
ok(disk(p)["sents"][3]["open"].get("seg") == [1, 3], "连成段：照旧在那句上记了 seg")

p, b = book({0}); cli("--i", "3")
os.utime(SQ, (b["made"] - 100, b["made"] - 100))
got = run_hook(QUIET)
ok(got is None and not SQ.exists(), "summoned.json 是上一个梦的：不递，删掉")

p, b = book({0}); b = disk(p); b["sents"][5]["open"] = {"t": time.time(), "how": "他自己的话", "by": "x"}; dreambook._save(p, b)
Q.write_text(json.dumps({"text": S[5]}, ensure_ascii=False)); cli("--i", "2")
got1 = run_hook(QUIET); q_left = Q.exists()
got2 = run_hook(QUIET)
ok(got1 == ONE.format(S[2]) and q_left, "同时有 queued.json：这一轮递唤的，queued 留着")
ok(got2 == "（昨晚的梦里好像还有一句：『" + S[5] + "』）" and not Q.exists(), "下一轮递 queued 那句（原文案）")

p, _ = book(range(6), told=True)
SQ.write_text(json.dumps([{"i": 2, "at": time.time()}])); Q.write_text(json.dumps({"text": S[5]}, ensure_ascii=False))
ok(run_hook(QUIET) is None and not SQ.exists() and not Q.exists(), "已经 told_all：不递，summoned.json 和 queued.json 都删了")

p, _ = book({0}); cli("--i", "2")
got = run_hook("讲完了")
ok(got is not None and got.startswith("（她把昨晚的梦讲到结尾了。") and not SQ.exists(), "唤了还没递、她说「讲完了」：走讲完了（整段都给），summoned.json 一起删")

p, _ = book({0}); b = disk(p); b["sents"][5]["open"] = {"t": time.time(), "how": "他自己的话", "by": "x"}; dreambook._save(p, b)
Q.write_text(json.dumps({"text": S[5]}, ensure_ascii=False)); SQ.write_text("{坏的")
got = run_hook(QUIET)
ok(got == "（昨晚的梦里好像还有一句：『" + S[5] + "』）" and not SQ.exists(), "summoned.json 是坏的 json：不出错，走原流程（递了 queued），坏文件删了")

p, _ = book({0}); SQ.write_text(json.dumps({"i": 2}))
ok(run_hook(QUIET) is None, "summoned.json 不是列表：当没有，钩子不哑")
p, _ = book({0, 2}); SQ.write_text(json.dumps([{"i": 2, "at": time.time()}, {"i": 9, "at": time.time()}, "x"]))
ok(run_hook(QUIET) is None and not SQ.exists(), "summoned.json 里的编号梦簿里不是「她唤的」（醒来开的 / 不存在）：不递")
p, _ = book({0}); cli("--i", "2"); _real_open = dlock.open_
_calls = []
def _open_once_boom(c):                          # 只让第一下（递唤的那句）解不开，后面原流程照常
    _calls.append(1)
    if len(_calls) == 1: raise RuntimeError("解不开")
    return _real_open(c)
dlock.open_ = _open_once_boom
try: got = run_hook(QUIET); err = None
except Exception as e: got, err = None, e
dlock.open_ = _real_open
ok(err is None and got is None and len(_calls) > 1 and SQ.exists(), "递唤的时解不开：吞掉，接着走原流程（她的话照常去勾），不抛到外面；summoned.json 留着（先拼好再删）")
ok(run_hook(QUIET) == ONE.format(S[2]) and not SQ.exists() and run_hook(QUIET) is None, "解得开了的下一轮：那句递出来，只递一遍")

p, _ = book({0}, pending=True); before = p.read_bytes()
s = cli("--i", "3")
ok(j(s) == {"ok": False, "why": "还没醒"} and p.read_bytes() == before and not SQ.exists(), "晨递还没递出去时唤：summon.py 回「还没醒」，梦簿和 summoned.json 都没动")
got = run_hook(QUIET)
ok(got is not None and got.startswith("🌙") and S[3] not in got and disk(p)["pending_morning"] is False, "晨递照常递出，里面没有那句")
s = cli("--i", "3")
ok(j(s) == {"ok": True, "i": 3} and how_of(p, 3) == "她唤的" and SQ.exists(), "晨递递出去之后再唤：成了")
ok(run_hook(QUIET) == ONE.format(S[3]), "下一轮「敲了一下」递出那句，只递这一遍")

# ---------- 三½、一堆 / 全部 ----------
print("三½、一堆 / 全部：dreambook.summon_many / summon_all")
import copy
def contiguous(xs): return all(xs[k + 1] == xs[k] + 1 for k in range(len(xs) - 1))
seen = set()
for _ in range(40):
    _, b = book({2}); r = dreambook.summon_many(b, 2); seen.add(tuple(r))
ok(seen == {(0, 1), (3, 4)}, f"一堆 k=2、已开 2：只挑紧挨着 2 的连续两句（40 次挑到 {sorted(seen)}）")
seen = set()
for _ in range(20):
    _, b = book({1, 2}); seen.add(tuple(dreambook.summon_many(b, 3)))
ok(seen == {(3, 4, 5)}, "一堆 k=3、已开 1、2：跳过开着的，从 3 往后长（0 那截只有一句不够长）")
seen = set(); allc = True
for _ in range(60):
    _, b = book(()); r = dreambook.summon_many(b, 3); seen.add(r[0]); allc = allc and len(r) == 3 and contiguous(r)
ok(allc and len(seen) >= 3 and seen <= {0, 1, 2, 3}, f"一堆 k=3、一句都没开：随机起点取连续三句（60 次起点 {sorted(seen)}）")
_, b = book({0, 1, 2}); r = dreambook.summon_many(b, 5)
ok(r == [3, 4, 5], "一堆 k=5、只剩 3 句没开：有几句唤几句")
_, b = book({1, 4}); r = dreambook.summon_many(b, 5)
ok(r == [2, 3] and all(b["sents"][x]["open"] is None for x in (0, 5)), "一堆 k=5、剩 4 句散在三截（0 / 2~3 / 5）：只取最长那截 2、3，不去别处补")
seen = set()
for _ in range(20):
    _, b = book({1, 4}); seen.add(tuple(dreambook.summon_many(b, 3)))
ok(seen == {(2, 3)}, "一堆 k=3、最长截只有两句：只给那一截、是连续的")
seen = set()
for _ in range(40):
    _, b = book({2}); r = dreambook.summon_many(b, 4); seen.add(tuple(r))
ok(seen == {(3, 4, 5)}, "一堆 k=4、两截（0~1 / 3~5）都不够长：只取最长的 3~5")
seen = set()
for _ in range(40):
    _, b = book({0, 3}); r = dreambook.summon_many(b, 3); seen.add(tuple(r))
ok(seen == {(1, 2), (4, 5)}, f"一堆 k=3、两截一样长（1~2 / 4~5）：随机挑一截整截给（{sorted(seen)}）")
p, b = book({0}); r = dreambook.summon_many(b, 3)
ok(r == [1, 2, 3] and all(set(b["sents"][x]["open"]) == {"t", "how"} and b["sents"][x]["open"]["how"] == "她唤的" for x in r)
   and all(b["sents"][x]["open"] is None for x in (4, 5)) and disk(p)["sents"][1]["open"] is None, "一堆：回升序编号，每句 {t, how: 她唤的}，别的没动，不存盘")
_, b = book({0}); b0 = copy.deepcopy(b)
ok(all(dreambook.summon_many(b, k) is None and dreambook.summon_why(b, k=k) == "编号不对" for k in (0, -1, -5, "3", 2.5, True, False, None)) and b == b0,
   "一堆 k 非法（0 / 负数 / 不是数 / bool / None）：不开，原因「编号不对」，梦簿没动")
ok(dreambook.summon_why(b, i=1, k=2) == "编号不对", "i 和 k 一起给：编号不对")
_, b = book(woke=False);          ok(dreambook.summon_many(b, 2) is None and dreambook.summon_all(b) is None and dreambook.summon_why(b, k=2) == "还没醒", "一堆 / 全部 没醒：还没醒")
_, b = book({0}, pending=True);   ok(dreambook.summon_many(b, 2) is None and dreambook.summon_all(b) is None and dreambook.summon_why(b, k=2) == "还没醒"
                                     and all(s["open"] is None for s in b["sents"][1:]), "一堆 / 全部 晨递还没递出去：还没醒，没动")
_, b = book({0}, told=True);      ok(dreambook.summon_many(b, 2) is None and dreambook.summon_all(b) is None and dreambook.summon_why(b, k=2) == "已经讲完了", "一堆 / 全部 讲完了：已经讲完了")
p, b = book({0, 3}); r = dreambook.summon_all(b)
ok(r == [1, 2, 4, 5] and all(b["sents"][x]["open"]["how"] == "她唤的" and set(b["sents"][x]["open"]) == {"t", "how"} for x in r)
   and b["sents"][0]["open"]["how"] == "醒来", "全部：回剩下的编号（升序），都标「她唤的」，原来开着的不动")
ok("told_all" not in b and dreambook.summon_why(b) == "没有可唤的了" and dreambook.summon_why(b, k=3) == "没有可唤的了"
   and dreambook.summon_all(b) is None and dreambook.summon_many(b, 3) is None and dreambook.summon(b) is None,
   "全部唤开之后：不设 told_all，再唤（一句 / 一堆 / 全部）都回「没有可唤的了」")
ok(dreambook.try_unlock(b, "嗯", "她的话")[1] != "她讲完了，收起来了", "全部唤开不等于讲完了：try_unlock 不当它收起来了")
def failing_open(n):
    calls = []
    real = dlock.open_
    def f(c):
        calls.append(1)
        if len(calls) == n: raise RuntimeError("解不开")
        return real(c)
    return f, real
for name, fn in (("一堆", lambda b: dreambook.summon_many(b, 4)), ("全部", dreambook.summon_all)):
    _, b = book({0}); b0 = copy.deepcopy(b); f, real = failing_open(3); dlock.open_ = f
    try: fn(b); err = None
    except Exception as e: err = e
    dlock.open_ = real
    ok(err is not None and b == b0, f"{name}：第三句解不开就整批不动（梦簿一句都没标）")

print("三½、一堆 / 全部：summon.py")
p, _ = book({0}); s = run_cli("--n", "3"); r = j(s)
ok(r == {"ok": True, "i": [1, 2, 3], "n": 3} and s.count("\n") == 1, "--n 3：{ok:true, i:[1,2,3], n:3}，只一行")
ok([how_of(p, x) for x in range(6)] == ["醒来", "她唤的", "她唤的", "她唤的", None, None], "--n 3：存了盘")
q = json.loads(SQ.read_text())
ok([x["i"] for x in q] == [1, 2, 3] and all(set(x) == {"i", "at"} for x in q), "--n 3：summoned.json 每句一项，只记编号，没有 all")
s = run_cli("--n=5"); ok(j(s) == {"ok": True, "i": [4, 5], "n": 2}, "--n=5 的写法也认；只剩两句就唤两句")
ok([x["i"] for x in json.loads(SQ.read_text())] == [1, 2, 3, 4, 5], "summoned.json 接着追加")
ok(j(run_cli("--n", "2")) == {"ok": False, "why": "没有可唤的了"} and j(run_cli("--all")) == {"ok": False, "why": "没有可唤的了"}, "全开了：--n / --all 都回「没有可唤的了」")
p, _ = book({0, 3}); s = run_cli("--all"); r = j(s)
ok(r == {"ok": True, "i": [1, 2, 4, 5], "n": 4} and s.count("\n") == 1, "--all：{ok:true, i:[1,2,4,5], n:4}")
ok("told_all" not in disk(p) and all(how_of(p, x) == "她唤的" for x in (1, 2, 4, 5)), "--all：盘上不设 told_all")
q = json.loads(SQ.read_text())
ok([x["i"] for x in q] == [1, 2, 4, 5] and all(x.get("all") is True and set(x) == {"i", "at", "all"} for x in q), "--all：排队的每项多记 all: true")
ok(j(run_cli("--all")) == {"ok": False, "why": "没有可唤的了"} and j(run_cli()) == {"ok": False, "why": "没有可唤的了"}, "--all 之后再唤：没有可唤的了")
p, _ = book({0}); s = run_cli("--i", "2"); ok(j(s) == {"ok": True, "i": 2} and set(j(s)) == {"ok", "i"}, "--i 的输出形状没变：{ok, i:整数}，没有 n")
p, _ = book({0}); before = p.read_bytes()
BAD = (("--n", "0"), ("--n", "-1"), ("--n", "abc"), ("--n", "2.5"), ("--n", "true"), ("--n",), ("--n=",), ("--n=x",), ("--all", "1"), ("--all=1",), ("--all", "--all"),
       ("--i", "1", "--all"), ("--all", "--i", "1"), ("--n", "2", "--i", "1"), ("--i=1", "--n=2"), ("--n", "2", "--all"), ("--n", "2", "--n", "3"), ("--N", "2"), ("-n", "2"), ("--many", "2"))
res = [j(run_cli(*a)) for a in BAD]
ok(all(r == {"ok": False, "why": "编号不对"} for r in res) and p.read_bytes() == before and not SQ.exists(),
   f"坏写法 {len(BAD)} 种（k 非法 / 缺值 / 混用 --i --n --all / 重复 / 拼错）：都回「编号不对」，梦簿和队列没动")
for a in (("--n", "2"), ("--all",)):
    p, _ = book(woke=False);          ok(j(run_cli(*a)) == {"ok": False, "why": "还没醒"}, f"{a[0]} 没醒：还没醒")
    p, _ = book({0}, pending=True); before = p.read_bytes()
    ok(j(run_cli(*a)) == {"ok": False, "why": "还没醒"} and p.read_bytes() == before and not SQ.exists(), f"{a[0]} 晨递还没递出去：还没醒，没动")
    p, _ = book({0}, told=True);      ok(j(run_cli(*a)) == {"ok": False, "why": "已经讲完了"} and not SQ.exists(), f"{a[0]} 讲完了：已经讲完了")
    clean();                          ok(j(run_cli(*a)) == {"ok": False, "why": "没有梦"}, f"{a[0]} 没有梦簿：没有梦")
    p, _ = book({0}); SQ.mkdir()
    s = run_cli(*a); SQ.rmdir()
    ok(j(s) == {"ok": False, "why": "出错了"} and all(how_of(p, x) is None for x in range(1, 6)) and how_of(p, 0) == "醒来", f"{a[0]} 排不进队：出错了，这批都关回去了")
    p, _ = book({0}); before = p.read_bytes(); dreambook._save = boom
    s = run_cli(*a); dreambook._save = _real_save
    ok(j(s) == {"ok": False, "why": "出错了"} and p.read_bytes() == before and not SQ.exists(), f"{a[0]} 存盘时炸：出错了，梦簿没动，没排队")
    p, _ = book({0}); before = p.read_bytes(); f, real = failing_open(2); dlock.open_ = f
    s = run_cli(*a); dlock.open_ = real
    ok(j(s) == {"ok": False, "why": "出错了"} and p.read_bytes() == before and not SQ.exists(), f"{a[0]} 有一句解不开：出错了，梦簿没动，没排队")
ok(not any(t in o or t[:4] in o for o in OUTS for t in S), f"到这里 {len(OUTS)} 次命令行输出里都没有句子的明文")
p, _ = book({0}); rc, o, e = sub("--n", "abc")
ok(rc == 0 and j(o) == {"ok": False, "why": "编号不对"} and e == "", "子进程 --n abc：退出码 0，编号不对")
rc, o, e = sub("--all", "--i", "1"); ok(rc == 0 and j(o) == {"ok": False, "why": "编号不对"}, "子进程 混用：退出码 0，编号不对")
rc, o, e = sub("--n", "2"); ok(rc == 0 and j(o) == {"ok": True, "i": [1, 2], "n": 2} and not any(t[:4] in o + e for t in S), "子进程 --n 2：退出码 0，没有明文")
rc, o, e = sub("--all"); ok(rc == 0 and j(o) == {"ok": True, "i": [3, 4, 5], "n": 3} and not any(t[:4] in o + e for t in S), "子进程 --all：退出码 0，没有明文")

print("三½、一堆 / 全部：钩子")
ALL = hook_before.SUMMON_ALL
ok(ALL == "（像有人把手伸进水里，一把把昨晚的梦整个捞了上来，还滴着水：\n{}\n）", "整本的文案：一字不差")
ok("她" not in ALL, "整本的文案里没有「她」字")
def lines(xs): return "\n".join("「" + S[x] + "」" for x in xs)
p, _ = book({0}); cli("--i", "4"); r = j(cli("--n", "2"))["i"]
got = run_hook(QUIET)
ok(r in ([1, 2], [2, 3]) and got == MANY.format(lines(sorted(r + [4]))), f"先唤 4 再一堆 {r}：一次用「敲了几下」给，按梦里顺序")
ok(run_hook(QUIET) is None and not SQ.exists(), "递完不再递")
p, _ = book({0, 3}); cli("--all")
got = run_hook(QUIET)
ok(got == ALL.format(lines(range(6))), "全部：用整本的文案，整本六句按梦里顺序（原来开着的也在里面）")
ok(run_hook(QUIET) is None and "told_all" not in disk(p), "整本递完：下一轮不再递，盘上没有 told_all")
p, _ = book({0}); cli("--n", "99")
ok(run_hook(QUIET) == MANY.format(lines(range(1, 6))), "--n 恰好把剩下的都唤开：用「敲了几下」，不是整本（只看她按的是什么）")
p, _ = book(range(5)); cli("--i", "5")
ok(run_hook(QUIET) == "（昨晚梦里的那一小段，又慢慢浮上来了：\n" + lines(range(6)) + "\n）", "--i 唤开最后一句：照旧走 recall（这里连成了段），不是整本")
p, _ = book(range(5)); cli("--all")
ok(run_hook(QUIET) == ALL.format(lines(range(6))), "只剩一句没开时按 --all：用整本的文案")
p, _ = book({0}); r1 = j(cli("--n", "2"))["i"]; r2 = j(cli("--all"))["i"]
q = json.loads(SQ.read_text())
ok([x.get("all") for x in q] == [None] * len(r1) + [True] * len(r2), "先 --n 后 --all：队列里前一批没有 all、后一批 all: true（追加时 all 键留着）")
got = run_hook(QUIET)
ok(got == ALL.format(lines(range(6))) and got.count(S[1]) == 1 and run_hook(QUIET) is None, "先 --n 后 --all、同一轮递：算全部，整本只递一遍，下一轮不再递")
p, b = book({0}); summon.enqueue(SQ, [3], b["made"], all_=True); summon.enqueue(SQ, [4], b["made"])
q = json.loads(SQ.read_text())
ok([(x["i"], x.get("all")) for x in q] == [(3, True), (4, None)], "enqueue：清理旧项时认得并留着 all 键，别的方式不记")
def hand_queue(items):
    p, _ = book({0}); b = disk(p)
    for x in (1, 2): b["sents"][x]["open"] = {"t": time.time(), "how": "她唤的"}
    dreambook._save(p, b); SQ.write_text(json.dumps(items))
    return p
hand_queue([{"i": 1, "at": time.time(), "all": "true"}, {"i": 2, "at": time.time(), "all": 1}])
ok(run_hook(QUIET) == MANY.format(lines([1, 2])), "队列里 all 是别的值（\"true\" / 1）：当没有，用「敲了几下」")
hand_queue([{"i": 1, "at": time.time()}, {"i": 2, "at": time.time()}])
ok(run_hook(QUIET) == MANY.format(lines([1, 2])), "旧队列没有 all 键：用「敲了几下」")
hand_queue([{"i": 1, "at": time.time(), "all": True}, {"i": 2, "at": time.time(), "all": False}])
ok(run_hook(QUIET) == ALL.format(lines([0, 1, 2])), "队列里有一项 all: true：用整本文案，列开着的句子按梦里顺序")
p, _ = book({0}); cli("--n", "1")
ok(run_hook(QUIET) == ONE.format(S[1]), "一堆 k=1（挨着 0 的只有 1）：只有一句，用「敲了一下」")
# 连成段去重：一堆递出去之后，再开一句接上来，不把整段再递一遍
p, _ = book({0}); r = j(cli("--n", "3"))["i"]
got = run_hook(QUIET)
ok(r == [1, 2, 3] and got == MANY.format(lines([1, 2, 3])), "一堆 1~3（挨着已开的 0）：用「敲了几下」给")
ok(disk(p)["sents"][3]["open"].get("seg") == [0, 3], "递完在这段编号最大那句上记了 seg=[0,3]（跟 segment 记的一样）")
got = run_hook("你梦里是不是有绿皮火车呀")
ok(got == "（昨晚梦里的那一小段，又慢慢浮上来了：\n接在那段后面：\n「" + S[4] + "」\n）", "之后她的话勾开 4：只给新接上的 4，不把 0~4 整段再递")
ok(not any(S[x] in got for x in (0, 1, 2, 3)), "那一轮里没有 0~3 的句子")
# 对照：不记 seg 时（改之前）会整段再递 —— 证明上面那条确实挡住了东西
p, _ = book({0}); cli("--n", "3"); _real_mark = dreambook.mark_given; dreambook.mark_given = lambda b, idxs: None
run_hook(QUIET); got = run_hook("你梦里是不是有绿皮火车呀"); dreambook.mark_given = _real_mark
ok(got is not None and S[1] in got and S[4] in got, "对照：不记的话，下一句会把 0~4 整段再递一遍（就是要挡的那种）")
p, _ = book({0}); cli("--n", "3"); _real_save2 = dreambook._save
def _save_boom_on_mark(pp, bb):
    if any((s.get("open") or {}).get("seg") for s in bb["sents"]): raise RuntimeError("炸了")
    return _real_save2(pp, bb)
dreambook._save = _save_boom_on_mark
try: got = run_hook(QUIET); err = None
except Exception as e: got, err = None, e
dreambook._save = _real_save2
ok(err is None and got == MANY.format(lines([1, 2, 3])), "记 seg 时存盘炸：照样递出去，不抛")
# 单句（--i）照旧：不记 seg，后面连成段的规矩跟以前一样
p, _ = book({0}); cli("--i", "1"); run_hook(QUIET)
ok(disk(p)["sents"][1]["open"].get("seg") is None, "单句唤（没连成段）：照旧不记 seg")

# ---------- 三¾、梦簿锁 / 先拼好再删 ----------
print("三¾、梦簿锁 / 先拼好再删")
import fcntl, threading
LOCKF = TMP / "dreambook.lock"
def hold():
    """在这个进程里另开一个 fd 占住锁（BSD flock 认打开的文件，同进程另一个 fd 也会被挡住，下面第一条验证这一点）。"""
    fd = os.open(str(LOCKF), os.O_RDWR | os.O_CREAT, 0o600); fcntl.flock(fd, fcntl.LOCK_EX); return fd
def release(fd): fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)
ok(summon.LOCK_WAIT == 10 and hook_before.LOCK_WAIT == 5 and hook_after.LOCK_WAIT == 5, "等锁上限：summon.py 10 秒，两个钩子 5 秒")
with dreambook.locked(1) as g: ok(g is True and LOCKF.exists(), "锁空着：拿到 True，锁文件在 DREAM_HOME 下叫 dreambook.lock")
fd = hold(); t0 = time.monotonic()
with dreambook.locked(0.3) as g: el = time.monotonic() - t0
release(fd)
ok(g is False and 0.25 <= el < 1.5, f"锁被占着：等到上限回 False（等了 {el:.2f} 秒）")
with dreambook.locked(0.3) as g: ok(g is True, "放了之后：又拿得到")
with dreambook.locked(0.3) as g1:
    with dreambook.locked(0.2) as g2: pass
ok(g1 is True and g2 is False, "同一个进程另开一次也会被挡（所以只在入口拿一次）")
try:
    with dreambook.locked(1) as g: raise ValueError("里面炸")
    err = None
except ValueError as e: err = e
with dreambook.locked(0.2) as g3: pass
ok(err is not None and g3 is True, "with 里面抛异常：异常照旧往外抛，锁放了")
LOCKF.unlink(); LOCKF.mkdir()
with dreambook.locked(0.2) as g: pass
LOCKF.rmdir()
ok(g is False, "锁文件开不了（被一个目录占着）：不抛，回 False")
_real_flock = fcntl.flock
def _flock_boom(*a): raise OSError("上锁炸了")
fcntl.flock = _flock_boom
with dreambook.locked(0.2) as g: pass
fcntl.flock = _real_flock
ok(g is False, "上锁本身抛 OSError：不抛，回 False")

# summon.py 拿不到锁
_real_wait = summon.LOCK_WAIT; summon.LOCK_WAIT = 0.3
for a in (("--i", "3"), ("--n", "2"), ("--all",), ()):
    p, _ = book({0}); before = p.read_bytes(); fd = hold()
    s = run_cli(*a); release(fd)
    ok(j(s) == {"ok": False, "why": "出错了"} and p.read_bytes() == before and not SQ.exists(), f"summon.py {' '.join(a) or '不带参数'} 拿不到锁：出错了，梦簿和队列都没动")
summon.LOCK_WAIT = _real_wait
p, _ = book({0}); fd = hold()
rc, o, e = sub("--i", "3"); release(fd)
ok(rc == 0 and j(o) == {"ok": False, "why": "出错了"} and e == "" and how_of(p, 3) is None and not SQ.exists(), "子进程 summon.py 拿不到锁（真等 10 秒）：出错了，退出码 0，没动")

# 钩子拿不到锁：照旧出该出的东西、不抛、大约 5 秒
LOG = TMP / "hook_err.log"
if LOG.exists(): LOG.unlink()
p, _ = book({0}); cli("--i", "3"); fd = hold(); t0 = time.monotonic()
try: got = run_hook(QUIET); err = None
except Exception as e: got, err = None, e
el = time.monotonic() - t0; release(fd)
ok(err is None and got == ONE.format(S[3]) and 4.9 <= el <= 6.5, f"钩子拿不到锁：等满 5 秒后照旧递出唤的那句，不抛（用了 {el:.1f} 秒）")
logtxt = LOG.read_text() if LOG.exists() else ""
ok(logtxt.count("梦簿锁没拿到") == 1 and not any(t[:4] in logtxt for t in S), "钩子拿不到锁：往 hook_err.log 记一行（没有梦的字）")
p, _ = book({0}); fd = hold(); t0 = time.monotonic()
got = run_hook("你梦里是不是有绿皮火车呀"); el = time.monotonic() - t0; release(fd)
ok(got == "（昨晚的梦里有一句：『" + S[4] + "』）" and how_of(p, 4) == "她的话" and el <= 6.5, "钩子拿不到锁：她的话照旧勾开一句、存盘")
p, _ = book({0}); cli("--i", "3")
fcntl.flock = _flock_boom; t0 = time.monotonic()
got = run_hook(QUIET); el = time.monotonic() - t0
fcntl.flock = _real_flock
ok(got == ONE.format(S[3]) and el < 2, "上锁抛异常：钩子马上照旧往下走")

# Stop 钩子：拿得到 / 拿不到都照旧
TR = TMP / "transcript.jsonl"
TR.write_text(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "我好像梦到绿皮火车了"}]}}, ensure_ascii=False) + "\n")
def run_stop():
    old_in = sys.stdin; sys.stdin = io.StringIO(json.dumps({"transcript_path": str(TR)}))
    try: hook_after.main()
    finally: sys.stdin = old_in
p, _ = book({3}); run_stop()
ok(how_of(p, 4) == "他自己的话" and json.loads(Q.read_text()).get("text") == S[4], "Stop 钩子（有锁）：他自己的话开了挨着的那句，排进 queued.json（行为跟原来一样）")
p, _ = book({3}); fd = hold(); t0 = time.monotonic(); run_stop(); el = time.monotonic() - t0; release(fd)
ok(how_of(p, 4) == "他自己的话" and Q.exists() and 4.9 <= el <= 6.5, f"Stop 钩子拿不到锁：等满 5 秒照旧走完（{el:.1f} 秒）")

# 交错：钩子读完梦簿之后 summon 才存盘排队
def interleave(use_lock):
    """钩子线程读完梦簿后在锁里睡 0.8 秒；这期间主线程跑 summon --i 3。回 (这一轮钩子的输出, summon 的结果, 下一轮钩子的输出)。"""
    p, _ = book({0})
    real_latest, real_locked = dreambook.latest, dreambook.locked
    read_done = threading.Event(); first = []
    def slow_latest():
        r = real_latest()
        if threading.current_thread().name == "hook" and not first:
            first.append(1); read_done.set(); time.sleep(0.8)
        return r
    @__import__("contextlib").contextmanager
    def no_lock(timeout): yield True
    dreambook.latest = slow_latest
    if not use_lock: dreambook.locked = no_lock
    box = {}
    th = threading.Thread(target=lambda: box.update(out=run_hook(QUIET)), name="hook"); th.start()
    read_done.wait(5)
    res = summon.run(["--i", "3"]); th.join(10)
    dreambook.latest, dreambook.locked = real_latest, real_locked
    return box.get("out"), res, run_hook(QUIET)
o1, res, o2 = interleave(use_lock=False)
ok(res == {"ok": True, "i": 3} and o1 is None and o2 is None, "对照（不加锁）：钩子读完之后 summon 才存盘 → 页面回 ok，可这句两轮都没递出去（就是要修的丢更新）")
o1, res, o2 = interleave(use_lock=True)
ok(res == {"ok": True, "i": 3} and o1 is None and o2 == ONE.format(S[3]), "加锁：summon 等钩子这一轮结束才动，下一轮把那句递出去")

# 先拼好再删
p, _ = book({0}); cli("--n", "2"); _calls.clear(); dlock.open_ = _open_once_boom
got = run_hook(QUIET); dlock.open_ = _real_open
ok(got is None and SQ.exists(), "一堆递的时候解不开：这一轮不递，summoned.json 留着")
ok(run_hook(QUIET) == MANY.format(lines([1, 2])) and not SQ.exists() and run_hook(QUIET) is None, "下一轮恢复：那两句递出来，只递一遍")
import pathlib
_real_unlink = pathlib.Path.unlink
def _unlink_boom(self, *a, **k):
    if self.name == "summoned.json": raise PermissionError("删不掉")
    return _real_unlink(self, *a, **k)
p, _ = book({0}); cli("--i", "3"); pathlib.Path.unlink = _unlink_boom
try: got1 = run_hook(QUIET); got2 = run_hook(QUIET)
finally: pathlib.Path.unlink = _real_unlink
ok(got1 == ONE.format(S[3]) and got2 is None and json.loads(SQ.read_text()) == [], "summoned.json 删不掉：照样递，文件换成空列表，下一轮不重递")
SQ.unlink()

shutil.rmtree(TMP, ignore_errors=True); shutil.rmtree(KEYDIR, ignore_errors=True)
print(f"\n共 {N} 条，过 {N - len(FAILS)} 条，没过 {len(FAILS)} 条。")
if FAILS:
    print("没过的：\n" + "\n".join("  - " + f for f in FAILS)); sys.exit(1)
print("全过。")
