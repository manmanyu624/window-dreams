"""影子：只剩一句的早上，另外给他的那一点：一个颜色、一种感觉、一个物件。

像人醒来「记不清了，但是有雨」。只给词，不给句子，让他自己顺着去想起来。
做法：梦做完、上锁之前，让一个小模型读整段，留下这三样，跟梦一起封进梦簿；早上抽到「只剩一句」才拿出来。
小模型我们用本机 ollama 里的 qwen3:8b，梦不出这台机器。换模型只改 _ask()。
提示词里不出现「梦」字（理由跟 shatter.py 一样）。

这个文件一大半是「把关」：小模型常常不守规矩（写成句子、照抄原文、直接把物件的名字说出来），
所以每样都要过 check_one()，不过就重问，问三次还不行就少给一样，宁可少给也不把梦说破。
"""
import json, os, re, urllib.request

OLLAMA = os.environ.get("DREAM_OLLAMA", "http://127.0.0.1:11434")
MODEL = os.environ.get("DREAM_SMALL_MODEL", "qwen3:8b")

PROMPT = """读完下面这段文字，只留下三样最淡的印象：一个颜色、一种感觉、一个物件。

要求：
- 每样都是一个词或很短的短语，不是句子，不带标点，不要解释。
- 颜色 2 到 6 个字。
- 感觉 2 到 6 个字：这段文字读完，身上哪里怎么了、或者心里怎么了，用刚睡醒的人随口嘟囔的大白话说，口语，短，笨一点也行，可以带「有点」「发」「的」「了」这类字。要贴着这一段自己的味道，换一段文字就该是另一个说法。不要四个字对仗的整齐词，不要成语，不要像标签。
- 物件 3 到 8 个字：从这段文字里挑一样真的出现过的东西，不说它叫什么，只说个大概，让人猜不准是哪样，像隔着雾看见的。写成「一个……的」或「一件……东西」这种样子，中间填它的用处、新旧、软硬、冷热之类，填的字要是你自己的话，不用文字里原有的词。例子（只是样子，不许照抄）：闹钟→一个会响的；木箱→一个装东西的；老怀表→一件旧东西。文字里出现过的物件名字一个都不要用。
- 用你自己的话概括，不要照抄原文里的长串。
- 只输出下面这三行，格式一字不差，别的什么都不要写：
颜色：……
感觉：……
物件：……

文字：
{body}

再说一遍：只输出三行，「颜色：」「感觉：」「物件：」各一行。"""

# 三样各自的字数范围
LIMITS = {"color": (2, 6), "feel": (2, 8), "thing": (3, 8)}
_LABELS = {"颜色": "color", "感觉": "feel", "物件": "thing"}
MAX_COPY = 6          # 连着照抄原文最多这么多个字，超过就不算
MAX_BODY = 6000       # 喂给模型的原文封顶，免得太长把提示词挤出上下文
# 物件只给个大概、避开原词（这是他自己要的：直接说出物件的名字，等于把那一句剧透了）：物件里任何连着的两个字一字不差出现在原文里就不算。
# 下面这张小表放行：说「大概」绕不开的通用字眼（东西、什么、数量词、指代），它们不指向具体哪样东西；带「的」的两个字也放行。
THING_OK = set("东西 什么 一件 一个 一种 一样 一些 一只 一把 一张 一块 一条 一台 一排 一串 一团 一片 一点 某个 某种 某样 某件 那个 那种 这个 这种 那件 这件 好像 不知".split())
_SENTENCE = "。！？!?；;，,、：:\n"     # 带这些就是句子（或者一串词），不是一个词
_EDGE = " \t\"'“”‘’「」『』《》【】[]()（）*`·"

def parse(raw):
    """把模型的回话解析成 {"color","feel","thing"}；只管格式，不管好坏。缺项、同一项出现两次回 None。
    容得下：多余空行、行首编号或小圆点、半角冒号、加粗星号、值两边的引号。"""
    if not isinstance(raw, str): return None
    got = {}
    for line in raw.splitlines():
        line = re.sub(r"^[\s\-•·*#>]*(?:\d+\s*[.、)）]\s*)?", "", line.strip()).strip()
        m = re.match(r"^\**\s*(颜色|感觉|物件)\s*\**\s*[：:]\s*(.*)$", line)
        if not m: continue
        key = _LABELS[m.group(1)]
        if key in got: return None
        got[key] = m.group(2).strip().strip(_EDGE).strip()
    return got if len(got) == 3 else None

def copied(value, text, n=MAX_COPY):
    """value 里有没有一段超过 n 个连续的字，一字不差出现在原文里。"""
    return any(value[k:k + n + 1] in text for k in range(len(value) - n))

def thing_echo(value, text):
    """物件里有没有连着的两个字一字不差出现在原文里（放行表里的和带「的」的不算）。"""
    for k in range(len(value) - 1):
        frag = value[k:k + 2]
        if frag in THING_OK or "的" in frag: continue
        if frag in text: return True
    return False

def check_one(key, v, text):
    """单看一样（key 是 color / feel / thing）：字数在范围里、不带句子的标点、没有照抄原文的长串；物件另外不许带原文里的词。
    过了回干净的字符串，不过回 None。"""
    if key not in LIMITS or not isinstance(v, str): return None
    v = v.strip(); lo, hi = LIMITS[key]
    if not (lo <= len(v) <= hi): return None
    if any(ch in v for ch in _SENTENCE) or "…" in v: return None
    if copied(v, text or ""): return None
    if key == "thing" and thing_echo(v, text or ""): return None
    return v

def check(d, text):
    """三样都得过 check_one。过了回干净的 dict，有一样不过就回 None。"""
    if not isinstance(d, dict): return None
    clean = {key: check_one(key, d.get(key), text) for key in LIMITS}
    return clean if all(v is not None for v in clean.values()) else None

def parse_and_check(raw, text):
    """解析 + 把关，测试里直接调这个，不碰模型。"""
    return check(parse(raw), text)

def _ask(text, temperature=0.3, avoid=None):
    """问一次小模型，回它的原话。超时就再试一次，第二次还不行往上抛。
    avoid：上一次因为带了原文的词被拒的那个物件，重问时告诉它别再这么写。"""
    prompt = PROMPT.format(body=text.strip()[:MAX_BODY])
    if avoid: prompt += f"\n物件不要再写「{avoid}」，里面用了文字里原有的词；换一样东西，或者换你自己的字来说。"
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=json.dumps({"model": MODEL, "prompt": prompt, "stream": False, "think": False, "options": {"temperature": temperature}}).encode(), headers={"Content-Type": "application/json"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r: return json.load(r)["response"]
        except (TimeoutError, OSError) as e:
            if attempt == 2: raise
            print(f"[shadow] 第 {attempt} 次 {type(e).__name__}，再试一次", flush=True)

TIMEOUT = 60          # 一次问话最多等这么久（平时一次 1~8 秒；别设太长，三次问话最坏会把整个做梦流程拖住）
ASKS = 3              # 最多问几次（数过：没留成的几乎全是物件撞了原文的两个字，所以重问时点名告诉它）

def make_shadow(text):
    """读整段，回 {"color","feel","thing"} 或 None。最多问 ASKS 次，哪次三样全过就用哪次。
    都没全过、但有哪次颜色和感觉两样各自过了，就只留这两样：thing 回空串（取最早过的那次）。颜色或感觉也过不了才回 None。
    模型连不上（重试过还不行）会往上抛，调用的人自己兜：影子没留成不该让这一夜的梦也没了。"""
    if not text or not text.strip(): return None
    avoid, two = None, None
    for attempt in range(1, ASKS + 1):
        # 真调时发现：低温下原样重问，它会原样再答一遍。所以重问时温度调高一点，并且要是上次栽在物件带原词上，就点名告诉它
        raw = _ask(text, temperature=(0.3 if attempt == 1 else 0.8), avoid=avoid)
        d = parse(raw)
        got = check(d, text)
        if got: return got
        if d:
            c, f = check_one("color", d.get("color"), text), check_one("feel", d.get("feel"), text)
            if two is None and c and f: two = {"color": c, "feel": f, "thing": ""}
            th = d.get("thing") or ""
            if LIMITS["thing"][0] <= len(th) <= LIMITS["thing"][1] and thing_echo(th, text): avoid = th
        if attempt < ASKS: print("[shadow] 回话不合规矩，再问一次", flush=True)      # 不打印回话本身，日志里不留字
    return two
