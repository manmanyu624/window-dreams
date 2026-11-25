#!/usr/bin/env python3
"""影子的测试。纯 Python：python3 test_shadow.py，有一条不过就非零退出。
不调模型（shadow.make_shadow / embed.embed 都换成假的），不碰真的梦：DREAM_HOME 指到临时目录，梦全是编的。
上锁用临时的钥匙文件（DREAM_KEY_FILE），不碰钥匙串；要有系统自带的 openssl。"""
import io, json, os, shutil, sys, tempfile, time
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="test_shadow_"))
KEYDIR = Path(tempfile.mkdtemp(prefix="test_shadow_key_"))
os.environ.pop("DREAM_KEY", None)
os.environ["DREAM_KEY_FILE"] = str(KEYDIR / "key")   # 钥匙走临时文件，不走钥匙串；必须在 import 之前定好
os.environ["DREAM_HOME"] = str(TMP)            # 必须在 import dreambook 之前定好
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "零件"))
import dreambook, embed, shadow, hook_before
dlock = dreambook.dlock

assert dreambook.BOOK == TMP / "梦簿", "梦簿没指到临时目录，停"

FAILS, N = [], 0
def ok(cond, name):
    global N
    N += 1
    print(("  过  " if cond else "  没过 ") + name)
    if not cond: FAILS.append(name)

# 编的假梦
FAKE = ("我站在一座很长的木桥上，桥下面的水是灰蓝色的。有人在对岸喊我的名字，声音却像从水底下传上来的。"
        "我低头看手里，握着一把生了锈的铜钥匙。桥板一块一块地往后退，我怎么走都走不到头。"
        "后来下起了小雨，雨点落在水面上没有声音。")
SH = {"color": "灰蓝色", "feel": "走不到头的慌", "thing": "一件开门的旧东西"}

# ---------- 一、解析与把关（不调模型） ----------
print("一、解析与把关")
pc = shadow.parse_and_check
ok(pc("颜色：灰蓝色\n感觉：走不到头的慌\n物件：一件开门的旧东西", FAKE) == SH, "正常三行")
ok(pc("\n\n颜色：灰蓝色\n\n感觉：走不到头的慌\n\n物件：一件开门的旧东西\n\n", FAKE) == SH, "多余空行")
ok(pc("1. 颜色：灰蓝色\n2. 感觉：走不到头的慌\n3. 物件：一件开门的旧东西", FAKE) == SH, "行首编号")
ok(pc("- 颜色: 灰蓝色\n- 感觉: 走不到头的慌\n- 物件: 一件开门的旧东西", FAKE) == SH, "小圆点 + 半角冒号")
ok(pc("**颜色**：「灰蓝色」\n**感觉**：走不到头的慌\n**物件**：一件开门的旧东西", FAKE) == SH, "加粗和引号")
ok(pc("好的，下面是结果：\n颜色：灰蓝色\n感觉：走不到头的慌\n物件：一件开门的旧东西", FAKE) == SH, "前面多一行废话")
ok(pc("物件：一件开门的旧东西\n颜色：灰蓝色\n感觉：走不到头的慌", FAKE) == SH, "顺序乱了也认")
def th(x): return pc(f"颜色：灰蓝色\n感觉：走不到头的慌\n物件：{x}", FAKE)
ok(th("桥") is None and th("旧物") is None, "物件不到 3 个字，拒")
ok(th("一件说不清是什么的旧东西") is None, "物件超过 8 个字，拒")
ok(th("铜钥匙") is None, "具体物件、原文里有（铜钥匙），拒")
ok(th("一把钥匙") is None and th("旧木桥") is None and th("生了锈的") is None, "带原文里连着的两个字（钥匙 / 木桥 / 了锈），拒")
ok(th("一件旧东西") is not None and th("一个装东西的") is not None and th("一个会响的") is not None, "大概的说法，过")
ok(th("一把开门的") is not None and th("一个什么东西") is not None, "放行表里的片段（一把 / 一个 在原文里也有）不误杀")
ok("一把" in FAKE and "一块" in FAKE and shadow.thing_echo("一把钥匙", FAKE) and not shadow.thing_echo("一把一块东西", FAKE), "thing_echo：放行表只放通用字眼，不放物件名")
ok(th("水底下的") is None and th("桥下面的") is None, "带「的」的两个字放行，但旁边的原词（水底 / 桥下）照样拒")
ok(pc("颜色：灰蓝色\n感觉：握着钥匙的慌\n物件：一件旧东西", FAKE) is not None, "这道只管物件：感觉里带原文的词不拒")
ok(pc("颜色：灰蓝色\n物件：一件开门的旧东西", FAKE) is None, "缺一项，拒")
ok(pc("颜色：灰蓝色\n感觉：\n物件：一件开门的旧东西", FAKE) is None, "某项是空的，拒")
ok(pc("颜色：灰蓝色\n颜色：铁锈红\n感觉：慌\n物件：一件开门的旧东西", FAKE) is None, "同一项出现两次，拒")
ok(pc("颜色：灰蓝色\n感觉：很慌。\n物件：一件开门的旧东西", FAKE) is None, "带句号，拒")
ok(pc("颜色：灰蓝色\n感觉：慌，又有点冷\n物件：一件开门的旧东西", FAKE) is None, "带逗号（一串词），拒")
ok(pc("颜色：灰蓝色\n感觉：怎么走也走不到尽头的那种慌张\n物件：一件开门的旧东西", FAKE) is None, "感觉超长，拒")
ok(pc("颜色：灰蓝色带一点点铁锈红\n感觉：慌\n物件：一件开门的旧东西", FAKE) is None, "颜色超长，拒")
ok(pc("颜色：蓝\n感觉：慌张\n物件：一件开门的旧东西", FAKE) is None, "颜色只有一个字，拒")
ok(pc("颜色：灰蓝色\n感觉：怎么走都走不到头\n物件：一件开门的旧东西", FAKE) is None, "感觉照抄原文 8 个连续的字，拒")
ok(pc("颜色：灰蓝色\n感觉：走都走不到头啊\n物件：一件开门的旧东西", FAKE) is not None, "只跟原文连着重合 6 个字，过")
ok(pc("", FAKE) is None and pc(None, FAKE) is None and pc("想不出来", FAKE) is None, "空的 / None / 不成格式，拒")
ok(shadow.copied("怎么走都走不到", FAKE) and not shadow.copied("走都走不到头", FAKE), "copied：7 个连续字算抄，6 个不算")

# make_shadow 的重试：把 _ask 换成假的，数它被问了几次
print("一补、make_shadow 的重试（_ask 换成假的）")
_real_ask = shadow._ask
def fake_ask(replies):
    calls = []
    def f(text, temperature=0.3, avoid=None):
        calls.append((temperature, avoid)); return replies[min(len(calls), len(replies)) - 1]
    return f, calls
good, bad = "颜色：灰蓝色\n感觉：走不到头的慌\n物件：一件开门的旧东西", "这段文字讲的是一座桥。"
shadow._ask, c = fake_ask([good]);      ok(shadow.make_shadow(FAKE) == SH and len(c) == 1, "第一次就合规矩：问 1 次")
shadow._ask, c = fake_ask([bad, good]); ok(shadow.make_shadow(FAKE) == SH and len(c) == 2, "第一次不合规矩：重问 1 次后过")
shadow._ask, c = fake_ask([bad, bad, bad]);  ok(shadow.make_shadow(FAKE) is None and len(c) == 3, "三次都不成格式：回 None，总共只问 3 次")
shadow._ask, c = fake_ask([good]);      ok(shadow.make_shadow("  ") is None and len(c) == 0, "空文字：不问模型，回 None")
echo = "颜色：灰蓝色\n感觉：走不到头的慌\n物件：一把铜钥匙"
shadow._ask, c = fake_ask([echo, good]); ok(shadow.make_shadow(FAKE) == SH and c == [(0.3, None), (0.8, "一把铜钥匙")], "物件带原词被拒：重问时温度调高，并点名别再写那个")
shadow._ask, c = fake_ask([bad, good]);  ok(shadow.make_shadow(FAKE) == SH and c == [(0.3, None), (0.8, None)], "别的原因被拒：重问时不点名")
echo2 = "颜色：灰蓝\n感觉：慌张\n物件：一座旧木桥"
TWO = {"color": "灰蓝色", "feel": "走不到头的慌", "thing": ""}
shadow._ask, c = fake_ask([echo, echo2, good]); ok(shadow.make_shadow(FAKE) == SH and c == [(0.3, None), (0.8, "一把铜钥匙"), (0.8, "一座旧木桥")], "第三次才过：用第三次的，第 2、3 次都高温并点名上一次撞了的物件")
shadow._ask, c = fake_ask([bad, echo, good]);   ok(shadow.make_shadow(FAKE) == SH and c == [(0.3, None), (0.8, None), (0.8, "一把铜钥匙")], "第一次不成格式、第二次撞、第三次过")
shadow._ask, c = fake_ask([echo, echo2, echo]); ok(shadow.make_shadow(FAKE) == TWO and len(c) == 3, "三次物件都撞原文：只留颜色和感觉，thing 是空串，取最早过的那次")
shadow._ask, c = fake_ask([bad, echo2, echo]);  ok(shadow.make_shadow(FAKE) == {"color": "灰蓝", "feel": "慌张", "thing": ""}, "第一次不成格式：两样取后面最早过的那次")
longthing = "颜色：灰蓝色\n感觉：走不到头的慌\n物件：一件说不清是什么的旧东西"
shadow._ask, c = fake_ask([longthing]);         ok(shadow.make_shadow(FAKE) == TWO and c == [(0.3, None), (0.8, None), (0.8, None)], "物件是因为超长过不了：也留两样，重问不点名")
badcolor = "颜色：蓝\n感觉：走不到头的慌\n物件：一把铜钥匙"
shadow._ask, c = fake_ask([badcolor]);          ok(shadow.make_shadow(FAKE) is None and len(c) == 3, "颜色也不行（三次都是）：回 None")
badfeel = "颜色：灰蓝色\n感觉：怎么走都走不到头\n物件：一把铜钥匙"
shadow._ask, c = fake_ask([badfeel]);           ok(shadow.make_shadow(FAKE) is None, "感觉照抄原文（三次都是）：回 None")
shadow._ask, c = fake_ask([badcolor, badfeel, echo2]); ok(shadow.make_shadow(FAKE) == {"color": "灰蓝", "feel": "慌张", "thing": ""}, "颜色、感觉得是同一次里都过才算：不跨次拼")
ok(shadow.check_one("color", "灰蓝色", FAKE) == "灰蓝色" and shadow.check_one("color", "蓝", FAKE) is None and shadow.check_one("thing", "铜钥匙", FAKE) is None
   and shadow.check_one("feel", "铜钥匙", FAKE) == "铜钥匙" and shadow.check_one("thing", None, FAKE) is None and shadow.check_one("别的", "灰蓝色", FAKE) is None, "check_one 单项判断")
shadow._ask = _real_ask

# ---------- 二、make：影子有 / 没有 / 抛异常，梦簿都能写出 ----------
print("二、dreambook.make")
embed.embed = lambda texts: [[0.1, 0.2, 0.3] for _ in texts]      # 假向量，不依赖 ollama
assert dlock.open_(dlock.seal("试一下")) == "试一下", "上锁用不了（要有 openssl），停"

def boom(text): raise RuntimeError("模型炸了")
def load(day): return json.loads((dreambook.BOOK / f"{day}.json").read_text())
BASE_KEYS = {"day", "made", "sents", "src", "guesses", "made_hm"}       # 现在的梦簿顶层就这六个字段
n_sents = len(dreambook.split(FAKE))

shadow.make_shadow = lambda text: dict(SH)
n = dreambook.make("2001-01-01", FAKE, {"来源": "编的"}, made_hm="05:20"); b1 = load("2001-01-01")
ok(n == n_sents and len(b1["sents"]) == n_sents, "有影子：梦簿写出，句数对")
ok(set(b1) == BASE_KEYS | {"shadow"}, "有影子：顶层只多一个 shadow 字段")
ok(isinstance(b1["shadow"], str) and "灰蓝" not in b1["shadow"] and "灰蓝" not in json.dumps(b1, ensure_ascii=False), "有影子：是封起来的，盘上看不到明文")
ok(dreambook.shadow_of(b1) == SH, "有影子：shadow_of 解出来一样")
ok([dlock.open_(s["c"]) for s in b1["sents"]] == dreambook.split(FAKE) and json.loads(dlock.open_(b1["src"])) == {"来源": "编的"}, "有影子：句子和来源没被动过")

shadow.make_shadow = lambda text: None
n = dreambook.make("2001-01-02", FAKE, {"来源": "编的"}, made_hm="05:20"); b2 = load("2001-01-02")
ok(n == n_sents and set(b2) == BASE_KEYS, "影子回 None：梦簿写出，没有 shadow 字段")
ok(dreambook.shadow_of(b2) is None, "影子回 None：shadow_of 回 None")

shadow.make_shadow = boom
n = dreambook.make("2001-01-03", FAKE, {"来源": "编的"}, made_hm="05:20"); b3 = load("2001-01-03")
ok(n == n_sents and set(b3) == BASE_KEYS, "影子抛异常：梦簿照样写出，没有 shadow 字段")

_real_seal = dlock.seal; seen = []
def seal_boom(t):
    if seen: raise RuntimeError("封不上")          # 第一次放过之后都炸：只让封影子那一下炸
    return _real_seal(t)
shadow.make_shadow = lambda text: (seen.append(1), dict(SH))[1]
dlock.seal = lambda t: seal_boom(t)
n = dreambook.make("2001-01-04", FAKE, {"来源": "编的"}, made_hm="05:20"); b4 = load("2001-01-04")
dlock.seal = _real_seal
ok(n == n_sents and set(b4) == BASE_KEYS and len(b4["sents"]) == n_sents, "封影子时炸了：梦簿照样写出，没有 shadow 字段")

# 影子没留成要往 hook_err.log 记一行：只有时刻、「影子没留成」、原因，不带梦的字
print("二补、影子没留成的日志（hook_err.log）")
import re
LOG = TMP / "hook_err.log"
lines = LOG.read_text(encoding="utf-8").splitlines() if LOG.exists() else []
pat = r"\d\d-\d\d \d\d:\d\d 影子没留成 "
ok(len(lines) == 3, f"前面四次 make：成了的那次不记，没成的三次各记一行（实际 {len(lines)} 行）")
ok(len(lines) == 3 and re.fullmatch(pat + "不合规矩", lines[0]) is not None, "回 None：记「影子没留成 不合规矩」")
ok(len(lines) == 3 and all(re.fullmatch(pat + "RuntimeError", l) for l in lines[1:]), "抛异常 / 封不上：记「影子没留成 RuntimeError」，只有类型名")
ok("模型炸了" not in "".join(lines) and "封不上" not in "".join(lines), "日志里没有异常里的话")
ok(not any(sent[:4] in "".join(lines) for sent in dreambook.split(FAKE)) and not any(v in "".join(lines) for v in SH.values()), "日志里没有梦的字，也没有影子的字")
# 记不了日志（hook_err.log 的位置被一个目录占着）也不能影响梦簿
LOG.unlink(); LOG.mkdir()
shadow.make_shadow = boom
n = dreambook.make("2001-01-05", FAKE, {"来源": "编的"}, made_hm="05:20"); b5 = load("2001-01-05")
ok(n == n_sents and set(b5) == BASE_KEYS, "影子抛异常 + 日志也记不了：梦簿照样写出")
shadow.make_shadow = lambda text: None
n = dreambook.make("2001-01-06", FAKE, {"来源": "编的"}, made_hm="05:20"); b6 = load("2001-01-06")
ok(n == n_sents and set(b6) == BASE_KEYS, "影子回 None + 日志也记不了：梦簿照样写出")
LOG.rmdir()
shadow.make_shadow = lambda text: dict(SH)
dreambook.make("2001-01-07", FAKE, {"来源": "编的"}, made_hm="05:20")
ok(not LOG.exists() and "shadow" in load("2001-01-07"), "影子留成了：不记日志")
shadow.make_shadow = lambda text: dict(TWO)
n = dreambook.make("2001-01-08", FAKE, {"来源": "编的"}, made_hm="05:20"); b8 = load("2001-01-08")
ok(n == n_sents and set(b8) == BASE_KEYS | {"shadow"} and dreambook.shadow_of(b8) == TWO, "只留两样：梦簿写出，有 shadow 字段，解出来 thing 是空串")
lines = LOG.read_text(encoding="utf-8").splitlines() if LOG.exists() else []
ok(len(lines) == 1 and re.fullmatch(r"\d\d-\d\d \d\d:\d\d 影子只留了两样 物件带原词", lines[0]) is not None, "只留两样：记一行「影子只留了两样 物件带原词」，没有梦的字")
LOG.unlink(); LOG.mkdir()
n = dreambook.make("2001-01-09", FAKE, {"来源": "编的"}, made_hm="05:20")
ok(n == n_sents and dreambook.shadow_of(load("2001-01-09")) == TWO, "只留两样 + 日志记不了：梦簿和影子照样写出")
LOG.rmdir()

# ---------- 三、shadow_of ----------
print("三、shadow_of")
old = {k: v for k, v in b1.items() if k != "shadow"}
ok(dreambook.shadow_of(old) is None, "旧梦簿（没有 shadow 字段）回 None")
ok(dreambook.shadow_of(dict(old, shadow="这不是密文")) is None, "解不开回 None")
ok(dreambook.shadow_of(dict(old, shadow=dlock.seal("不是 json"))) is None, "解开了但不是 json 回 None")
ok(dreambook.shadow_of(dict(old, shadow=dlock.seal(json.dumps({"color": "灰蓝色"})))) is None, "解开了但缺项回 None")
ok(dreambook.shadow_of(dict(old, shadow=None)) is None, "shadow 是 None 回 None")
def sealed(d): return dict(old, shadow=dlock.seal(json.dumps(d, ensure_ascii=False)))
ok(dreambook.shadow_of(sealed(TWO)) == TWO, "thing 是空串：回两样 + 空串")
ok(dreambook.shadow_of(sealed({"color": "灰蓝色", "feel": "走不到头的慌"})) == TWO, "缺 thing 这个键：当空串")
ok(dreambook.shadow_of(sealed({"color": "灰蓝色", "feel": "", "thing": "一件旧东西"})) is None and dreambook.shadow_of(sealed({"color": " ", "feel": "慌", "thing": "一件旧东西"})) is None
   and dreambook.shadow_of(sealed({"feel": "慌", "thing": "一件旧东西"})) is None, "颜色或感觉是空的 / 缺了：回 None")

# ---------- 四、晨递文案 ----------
print("四、晨递文案（morning_text）")
def original(tier, sents):
    """没有影子时晨递原来的文案，原样抄在这里当对照。"""
    opened = [t for i, t in sents if t]
    if tier == "none" or not opened:
        text = "🌙 好像做了个梦，想不起来了。"
    elif tier == "one":
        text = f"🌙 昨晚好像做了个梦……只剩一句：「{opened[0]}」"
    else:
        lines, gap = [], False
        for i, t in sents:
            if t: lines.append(f"「{t}」"); gap = False
            elif not gap: lines.append("……这里想不起来了"); gap = True
        text = "🌙 昨晚好像做了个梦……\n" + "\n".join(lines)
    return text
S_ONE = [(0, None), (1, "有人在对岸喊我的名字。"), (2, None), (3, None)]
S_MOST = [(0, "我站在一座很长的木桥上。"), (1, None), (2, None), (3, "后来下起了小雨。")]
S_ALL = [(0, "我站在一座很长的木桥上。"), (1, "有人在对岸喊我的名字。")]
S_NIL = [(0, None), (1, None)]
mt = hook_before.morning_text
LINE = "\n别的醒来就散了，手里还剩一点：颜色是灰蓝色，心里走不到头的慌，旁边好像有一件开门的旧东西。"
ok(mt("one", S_ONE, SH) == original("one", S_ONE) + LINE, "one + 有影子：原文案后面正好多这一行")
ok(mt("one", S_ONE, SH) == "🌙 昨晚好像做了个梦……只剩一句：「有人在对岸喊我的名字。」\n别的醒来就散了，手里还剩一点：颜色是灰蓝色，心里走不到头的慌，旁边好像有一件开门的旧东西。", "one + 有影子：整段文案逐字对")
ok(mt("one", S_ONE, None) == original("one", S_ONE) and mt("one", S_ONE) == original("one", S_ONE), "one + 没影子：一字不差")
for tier, sents in (("most", S_MOST), ("all", S_ALL), ("none", S_ONE), ("none", S_NIL), ("one", S_NIL), ("most", S_NIL)):
    ok(mt(tier, sents, SH) == original(tier, sents) and mt(tier, sents) == original(tier, sents),
       f"{tier}（开着 {sum(1 for _, t in sents if t)} 句）给不给影子都一字不差")
ok(mt("one", S_ONE, {"color": "灰蓝色"}) == original("one", S_ONE), "one + 影子缺项：退回原文案")
ok(mt("one", S_ONE, "不是字典") == original("one", S_ONE), "one + 影子不成样子：退回原文案")
TAIL2 = "\n别的醒来就散了，手里还剩一点：颜色是灰蓝色，心里走不到头的慌。"
ok(mt("one", S_ONE, TWO) == original("one", S_ONE) + TAIL2, "one + thing 是空串：「…颜色是X，心里Y。」")
ok(mt("one", S_ONE, {"color": "灰蓝色", "feel": "走不到头的慌"}) == original("one", S_ONE) + TAIL2 and mt("one", S_ONE, dict(TWO, thing=None)) == original("one", S_ONE) + TAIL2, "one + 缺 thing 键 / thing 是 None：一样")
ok(mt("one", [(0, "桥下面的水是灰蓝色的。")], TWO) == original("one", [(0, "桥下面的水是灰蓝色的。")]) + "\n别的醒来就散了，手里还剩一点：心里走不到头的慌。", "thing 空 + 颜色在那句里：只剩「心里Y。」")
ok(mt("one", [(0, "灰蓝色的水，走不到头的慌。")], TWO) == original("one", [(0, "灰蓝色的水，走不到头的慌。")]), "thing 空 + 两样都在那句里：不加这一行")
for tier, sents in (("most", S_MOST), ("all", S_ALL), ("none", S_ONE)):
    ok(mt(tier, sents, TWO) == original(tier, sents), f"{tier} + 只有两样的影子：一字不差")

# 影子跟那一句重复：哪一样的字整个在那一句里，就不说那一样
print("四补、影子跟那一句重复")
HEAD = "\n别的醒来就散了，手里还剩一点："
def one(sentence): return [(0, None), (1, sentence), (2, None)]
def base(sentence): return original("one", one(sentence))
s_key = "我低头看手里，握着一件开门的旧东西。"
ok(mt("one", one(s_key), SH) == base(s_key) + HEAD + "颜色是灰蓝色，心里走不到头的慌。", "物件在那句里：只说颜色和感觉，没有「旁边好像有」")
s_col = "桥下面的水是灰蓝色的。"
ok(mt("one", one(s_col), SH) == base(s_col) + HEAD + "心里走不到头的慌，旁边好像有一件开门的旧东西。", "颜色在那句里：只说感觉和物件")
s_feel = "心里全是走不到头的慌张。"
ok(mt("one", one(s_feel), SH) == base(s_feel) + HEAD + "颜色是灰蓝色，旁边好像有一件开门的旧东西。", "感觉在那句里：只说颜色和物件")
s_cf = "灰蓝色的水面上只有走不到头的慌。"
ok(mt("one", one(s_cf), SH) == base(s_cf) + HEAD + "旁边好像有一件开门的旧东西。", "颜色和感觉都在：只剩「旁边好像有…。」")
s_ct = "灰蓝色的水里沉着一件开门的旧东西。"
ok(mt("one", one(s_ct), SH) == base(s_ct) + HEAD + "心里走不到头的慌。", "颜色和物件都在：只剩「心里…。」")
s_ft = "握着一件开门的旧东西，只有走不到头的慌。"
ok(mt("one", one(s_ft), SH) == base(s_ft) + HEAD + "颜色是灰蓝色。", "感觉和物件都在：只剩「颜色是…。」")
s_all = "灰蓝色的桥上我握着一件开门的旧东西，只有走不到头的慌。"
ok(mt("one", one(s_all), SH) == base(s_all), "三样都在那句里：不加这一行，跟原文案一字不差")
s_part = "我握着一件旧东西，水是蓝色的。"
ok(mt("one", one(s_part), SH) == base(s_part) + LINE, "只重合一部分字不算重复：三样照说")

# ---------- 五、钩子整轮走一遍（临时目录里的假梦簿） ----------
print("五、钩子整轮（hook_before.main）")
def run_hook(prompt):
    old_in = sys.stdin; sys.stdin = io.StringIO(json.dumps({"prompt": prompt})); buf = io.StringIO()
    try:
        with redirect_stdout(buf): hook_before.main()
    finally: sys.stdin = old_in
    s = buf.getvalue().strip()
    return json.loads(s)["hookSpecificOutput"]["additionalContext"] if s else None
def fresh(tier, with_shadow, give):
    """清空临时梦簿，做一本今天的假梦簿，摆成「醒过了、等晨递」的样子。"""
    for f in dreambook.BOOK.glob("*.json"): f.unlink()
    day = date.today().isoformat()
    shadow.make_shadow = (lambda text: dict(SH)) if with_shadow else (lambda text: None)
    dreambook.make(day, FAKE, {"来源": "编的"}, made_hm="05:20")
    p, b = dreambook.today(day)
    for s in b["sents"]:
        if s["i"] in give: s["open"] = {"t": time.time(), "how": "醒来", "by": tier}
    b["woke"] = {"at": datetime.now().astimezone().isoformat(), "tier": tier, "gap_min": 200}
    b["pending_morning"] = True
    dreambook._save(p, b)
    return p, [(s["i"], dlock.open_(s["c"]) if s["open"] else None) for s in b["sents"]]

p, sents = fresh("one", True, {1})
got = run_hook("早呀"); after = json.loads(p.read_text())
ok(got == original("one", sents) + LINE, "one + 有影子：钩子递出来多一行")
ok(isinstance(after.get("shadow_given"), float) and after["pending_morning"] is False, "one + 有影子：同一次存盘记了 shadow_given，pending_morning 关了")
ok("影子" not in (run_hook("今天天气不错呀朋友") or "") and "影子" not in (run_hook("再说一句不相干的") or ""), "后面两轮不再递影子")

p, sents = fresh("one", False, {1})
got = run_hook("早呀"); after = json.loads(p.read_text())
ok(got == original("one", sents) and "shadow_given" not in after, "one + 没影子（等于旧梦簿）：一字不差，不记 shadow_given")

p, sents = fresh("most", True, {0, 1, 3})
got = run_hook("早呀"); after = json.loads(p.read_text())
ok(got == original("most", sents) and "shadow_given" not in after, "most + 有影子：一字不差，不记 shadow_given")

p, sents = fresh("all", True, set(range(n_sents)))
got = run_hook("早呀"); after = json.loads(p.read_text())
ok(got == original("all", sents) and "shadow_given" not in after, "all + 有影子：一字不差，不记 shadow_given")

p, sents = fresh("none", True, set())
got = run_hook("早呀"); after = json.loads(p.read_text())
ok(got == "🌙 好像做了个梦，想不起来了。" and "shadow_given" not in after, "none + 有影子：一字不差，不记 shadow_given")

p, sents = fresh("one", True, {1})
_real_of = dreambook.shadow_of
dreambook.shadow_of = boom
got = run_hook("早呀"); after = json.loads(p.read_text())
dreambook.shadow_of = _real_of
ok(got == original("one", sents) and "shadow_given" not in after and after["pending_morning"] is False, "one + 解影子时炸了：退回原文案，钩子没哑")

# 物件在那一句里：少说一截，照样记 shadow_given
p, sents = fresh("one", True, {2})
_real_of = dreambook.shadow_of
dreambook.shadow_of = lambda b: dict(SH, thing=sents[2][1][-6:-1])
got = run_hook("早呀"); after = json.loads(p.read_text())
dreambook.shadow_of = _real_of
ok(got == original("one", sents) + HEAD + "颜色是灰蓝色，心里走不到头的慌。" and isinstance(after.get("shadow_given"), float), "one + 物件在那一句里：少说一截，照样记 shadow_given")
# 三样全在那一句里：不加影子行，也不记 shadow_given
p, sents = fresh("one", True, {2})
_real_of = dreambook.shadow_of
dreambook.shadow_of = lambda b: {"color": sents[2][1][:3], "feel": sents[2][1][3:6], "thing": sents[2][1][6:8]}
got = run_hook("早呀"); after = json.loads(p.read_text())
dreambook.shadow_of = _real_of
ok(got == original("one", sents) and "shadow_given" not in after and after["pending_morning"] is False, "one + 三样全在那一句里：一字不差，不记 shadow_given")

# 整轮：做梦时就只留了两样（thing 空串），早上只剩一句
for f in dreambook.BOOK.glob("*.json"): f.unlink()
day = date.today().isoformat()
shadow.make_shadow = lambda text: dict(TWO)
dreambook.make(day, FAKE, {"来源": "编的"}, made_hm="05:20")
p, b = dreambook.today(day)
b["sents"][1]["open"] = {"t": time.time(), "how": "醒来", "by": "one"}
b["woke"] = {"at": datetime.now().astimezone().isoformat(), "tier": "one", "gap_min": 200}; b["pending_morning"] = True
dreambook._save(p, b)
sents = [(s_["i"], dlock.open_(s_["c"]) if s_["open"] else None) for s_ in b["sents"]]
got = run_hook("早呀"); after = json.loads(p.read_text())
ok(got == original("one", sents) + TAIL2 and isinstance(after.get("shadow_given"), float) and after["pending_morning"] is False, "整轮 one + thing 为空：递「…颜色是X，心里Y。」，记 shadow_given")

shutil.rmtree(TMP, ignore_errors=True); shutil.rmtree(KEYDIR, ignore_errors=True)
print(f"\n共 {N} 条，过 {N - len(FAILS)} 条，没过 {len(FAILS)} 条。")
if FAILS:
    print("没过的：\n" + "\n".join("  - " + f for f in FAILS)); sys.exit(1)
print("全过。")
