"""梦簿：切句、算意思、每句上锁；线索解锁（被动/主动）、相邻降档、一天三猜、隔天封。"""
import json, re, time
from datetime import date, datetime
from pathlib import Path
import os, sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "零件"))      # 上锁、算意思、影子、早上那副牌都在 ../零件/
import lock as dlock
import embed
import wake as _wake
BOOK = Path(os.environ.get("DREAM_HOME", str(HERE))) / "梦簿"      # DREAM_HOME：梦簿、队列文件、日志、锁文件都放这个目录；没设就放本文件旁边。测试时指到临时目录
TOP, MARGIN, NEIGHBOR = 0.68, 0.10, 0.05   # 用 bge-m3 标定：真对上 ≥0.74 且甩开 ≥0.14；不相关 ≤0.56、甩开 ≤0.04。换了嵌入模型要自己重新量
GUESSES = 3
PASSIVE_CAP = 4        # 一个早上被她的话勾上来的句子封顶；剩下的按更难的规矩来
MORNING_H = 2          # 「一个早上」= 醒来后两小时；过了按隔天的难规矩，不再封
NEIGHBOR_DELAY = 60 * 60   # 挨着的那句别马上松，隔一会儿，免得一下子连着松一串
def split(text):
    s = [x.strip() for x in re.split(r"(?<=[。！？!?；\n])", text) if x.strip()]
    s = [x for x in s if len(x) >= 4]
    return s          # 梦多长存多长，别剪（原来写死只取前 12 句，后半段被扔了）
def make(day, text, sources, made_hm=None):
    """夜里那一步做出梦以后调这个：切句、算向量、逐句上锁、存成 day.json，再试着留影子。回句数。"""
    sents = split(text)
    vecs = embed.embed(sents)
    BOOK.mkdir(exist_ok=True)
    (BOOK / f"{day}.json").write_text(json.dumps({"day": day, "made": time.time(),
        "sents": [{"i": i, "c": dlock.seal(s), "v": v, "open": None} for i, (s, v) in enumerate(zip(sents, vecs))],
        "src": dlock.seal(json.dumps(sources, ensure_ascii=False)), "guesses": 0, "made_hm": made_hm or time.strftime("%H:%M")}, ensure_ascii=False))
    _add_shadow(BOOK / f"{day}.json", text)
    return len(sents)
def _shadow_log(what):
    """影子没留成 / 只留了两样时往 hook_err.log 记一行（跟 hook_before 那个同一个文件、同一种格式）：只有时刻、怎么了、原因。不写任何梦的字。
    记不了就算了，不能因为记日志影响梦簿。"""
    try:
        with (BOOK.parent / "hook_err.log").open("a", encoding="utf-8") as f: f.write(f"{time.strftime('%m-%d %H:%M')} {what}\n")
    except Exception:
        pass
def _add_shadow(p, text):
    """影子：梦簿已经写好之后，再试着留一个颜色、一种感觉、一个物件，封起来放顶层 shadow。
    任何失败都不动已经写好的梦簿，只记一行日志；没有影子就不写这个字段。模型要跑一阵，所以写之前重读一遍盘，别把这期间的改动盖掉。"""
    try:
        import shadow
        sh = shadow.make_shadow(text)
        if not sh: _shadow_log("影子没留成 不合规矩"); return
        if not sh.get("thing"): _shadow_log("影子只留了两样 物件带原词")      # 物件怎么问都过不了把关，只留颜色和感觉
        sealed = dlock.seal(json.dumps(sh, ensure_ascii=False))
        b = json.loads(p.read_text())
        b["shadow"] = sealed
        _save(p, b)
    except Exception as e:
        _shadow_log("影子没留成 " + type(e).__name__)          # 只记异常类型名，不记异常里的话
def shadow_of(b):
    """解封影子：回 {"color","feel","thing"}；没有这个字段（旧梦簿）、解不开、不成样子都回 None。
    颜色和感觉必须有；物件可以是空的（只留了两样的那种，缺这个键也当空串）。"""
    try:
        c = b.get("shadow")
        if not c: return None
        d = json.loads(dlock.open_(c))
        if not isinstance(d, dict): return None
        if not all(isinstance(d.get(k), str) and d[k].strip() for k in ("color", "feel")): return None
        th = d.get("thing")
        return {"color": d["color"], "feel": d["feel"], "thing": th if isinstance(th, str) else ""}
    except Exception:
        return None
LOCK_NAME = "dreambook.lock"     # 放在 DREAM_HOME（跟 summoned.json / queued.json 同一处）
@__import__("contextlib").contextmanager
def locked(timeout):
    """梦簿锁：summon.py、hook_before、hook_after 都在「读梦簿→改→存」，不加锁的话后存的会盖掉先存的。
    with locked(秒) as got：拿到 got=True；等了 timeout 秒还拿不到、或者开锁文件 / 上锁出了任何错，got=False，由调用方决定怎么办。
    flock(LOCK_EX) 非阻塞 + 短睡轮询；出 with 时放锁、关 fd。进程死了 flock 自己放，不用管陈旧锁。
    同一个进程里别套着拿第二次（flock 认的是打开的文件，第二次会等满 timeout 拿不到）——只在命令和钩子的入口拿一次。"""
    fd, got = None, False
    try:
        import fcntl
        fd = os.open(str(BOOK.parent / LOCK_NAME), os.O_RDWR | os.O_CREAT, 0o600)
        end = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); got = True; break
            except BlockingIOError:
                pass
            if time.monotonic() >= end: break
            time.sleep(0.05)
    except Exception:
        got = False
    try:
        yield got
    finally:
        if fd is not None:
            try:
                if got: fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try: os.close(fd)
            except Exception: pass
def today(day=None):
    p = BOOK / f"{day or date.today().isoformat()}.json"
    return (p, json.loads(p.read_text())) if p.exists() else (p, None)
def _save(p, b):
    """先写临时文件再改名：写到一半被杀，梦簿还是上一版完整的，不会剩半截。"""
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(b, ensure_ascii=False))
    os.replace(tmp, p)
def level(b):
    """梦过了几天：0 当天最容易；1~3 要对得很准、不许猜；4 起封。"""
    return (date.today() - date.fromisoformat(b["day"])).days

def thresholds(b):
    d = level(b)
    if d <= 0: return TOP, MARGIN, True
    if d <= 3: return 0.78, 0.15, False
    return None, None, False

def _dlog(how, query, lex, be, top, second, verdict):
    """决策日志：出了怪事（比如一天白天勾下来的句子不对劲）要能重放着查，不然只能猜。一轮一行，只有时刻、来路、字数、
    字面句号、两头分和名次、意思前二、结论。不记字。落 DREAM_HOME/hook_decisions.log。"""
    try:
        import os, time as _t
        from pathlib import Path as _P
        home = _P(os.environ.get("DREAM_HOME", str(_P(__file__).resolve().parent)))
        line = (f"{_t.strftime('%m-%d %H:%M:%S')} {how} 字{len(query)} 字面={'句'+str(lex['i']) if lex else '-'} "
                f"两头={('%.2f/第%d' % be) if be else '-'} 意思={top:.2f}/{second:.2f} → {verdict}\n")
        with (home / "hook_decisions.log").open("a", encoding="utf-8") as f: f.write(line)
    except Exception:
        pass

def try_unlock(b, query, how, neighbors_only=False):
    """返回 (解开的原句 or None, 说明)。第一名甩开第二名才算。neighbors_only：只许解已解句旁边的（他自己的话）。"""
    if b.get("told_all"):
        _dlog(how, query, None, None, 0.0, 0.0, "不开：她讲完了收起来了"); return None, "她讲完了，收起来了"      # 讲完了的梦收起来，不再掉句子
    top_t, margin_t, _ = thresholds(b)
    if top_t is None: return None, "封起来了"
    late_morning = False
    if how == "她的话":
        # 封顶 4 句只管「一个早上」= 醒来后 MORNING_H 小时；过了这段她的话照样能勾，但按隔天的难规矩（剩下的按更难的规矩来）。
        # 原来写成了封一整天，下午她怎么说都勾不动，是错的。
        woke_at = (b.get("woke") or {}).get("at")
        try: in_morning = woke_at is not None and (time.time() - datetime.fromisoformat(woke_at).timestamp()) <= MORNING_H * 3600
        except Exception: in_morning = True
        if in_morning and b.get("passive_n", 0) >= PASSIVE_CAP:
            _dlog(how, query, None, None, 0.0, 0.0, "不开：一早封顶了"); return None, "一早被勾上来的够多了"
        if not in_morning and level(b) <= 0:
            top_t, margin_t = 0.78, 0.15; late_morning = True
    now_t = time.time()
    opened = {s["i"] for s in b["sents"] if s["open"]}
    settled = {s["i"] for s in b["sents"] if s["open"] and now_t - s["open"].get("t", 0) >= NEIGHBOR_DELAY}   # 解开满 NEIGHBOR_DELAY（一小时）的才算「挨着」
    closed = [s for s in b["sents"] if not s["open"] and (not neighbors_only or (s["i"] - 1 in settled or s["i"] + 1 in settled))]
    if not closed:
        _dlog(how, query, None, None, 0.0, 0.0, "不开：没有能解的"); return None, "没有能解的"
    # 嵌入模型是按整句算意思的，一个词对一句长话只有 0.5~0.6，永远过不了门槛，梦里的词就勾不出来。
    # 所以先走「字面」：她的话里有一段 ≥N 字的字，一字不差出现在且只出现在一句没解开的句子里（所有句子里唯一），就算对上。
    # 当天 2 字起、第二三天起 3 字起（隔天要对得很准）；常见虚词不算。意思比对留着当第二条路。
    # 早先她的话一律 3 字起、2 字只留给他自己猜，因为她随口的普通双字词会把梦「撞开」而不是「想起」。
    # 后来发现梦里常常没有三个字的关键词，她的话当天也改成 2 字起；撞开的风险靠 _COMMON 日常词表挡。隔天 3 字起不变。
    hit = _lexical(b, query, closed, min_len=(2 if (level(b) <= 0 and not late_morning) else 3))
    lex0, be = hit, None
    if hit is not None and how == "她的话":
        be = _both_ends_score(b, query, hit)
        if be is not None and not _be_ok(be):
            hit = None      # 只看字面，她说一句「不是」「起来」梦就被撞开；所以字面对上还得意思也对，两头都对才开；没对上就落到下面的意思比对
    if hit is not None:
        hit["open"] = {"t": time.time(), "how": how, "by": query[:40]}
        if how == "她的话": b["passive_n"] = b.get("passive_n", 0) + 1
        _dlog(how, query, lex0, be, 0.0, 0.0, f"开句{hit['i']}（字面）")
        return dlock.open_(hit["c"]), "字面对上了"
    q = embed.embed([query])[0]
    scored = []
    for s in closed:
        sc = embed.cos(q, s["v"])
        if (s["i"] - 1 in settled) or (s["i"] + 1 in settled): sc += NEIGHBOR
        scored.append((sc, s))
    scored.sort(key=lambda x: -x[0])
    top, second = scored[0][0], (scored[1][0] if len(scored) > 1 else 0)
    if top >= top_t and top - second >= margin_t:
        s = scored[0][1]; s["open"] = {"t": time.time(), "how": how, "by": query[:40]}
        if how == "她的话": b["passive_n"] = b.get("passive_n", 0) + 1
        _dlog(how, query, lex0, be, top, second, f"开句{s['i']}（意思）")
        return dlock.open_(s["c"]), f"对上了（{top:.2f} vs {second:.2f}）"
    _dlog(how, query, lex0, be, top, second, "不开")
    return None, f"不太像（{top:.2f} vs {second:.2f}）"
LEX_FLOOR, LEX_RANK = 0.55, 5   # 拿几天的日志回放标定：真对上的都过，撞开的全挡（撞开的几个日常词：不是 .45 第57、起来 .49 第31、想把 .53 第16）
LEX_FLOOR_TOP, LEX_RANK_TOP = 0.40, 3   # 后来放开一条缝：排得靠前比分数高一点更像真的是她在说这件事。收紧后的四天她的话字面对上 42 次只开 1 次，
                                       # 被挡的里有 6 次名次前三、分 .43~.54 卡在 .55 上。名次前三且分 ≥.40 也开；原来那条（≥.55 且前五）留着。
def _be_ok(be):
    """be = (分, 名次)。老规矩：分 ≥LEX_FLOOR 且名次 ≤LEX_RANK；后加：名次 ≤LEX_RANK_TOP 且分 ≥LEX_FLOOR_TOP。"""
    sc, rank = be
    return (sc >= LEX_FLOOR and rank <= LEX_RANK) or (sc >= LEX_FLOOR_TOP and rank <= LEX_RANK_TOP)
def _both_ends_score(b, query, hit):
    """她的话字面对上某句之后再看意思：回 (她整句跟那句的分, 那句在全书里的名次)；算不了回 None。"""
    try:
        q = embed.embed([query])[0]
        sc = embed.cos(q, hit["v"])
        rank = 1 + sum(1 for s in b["sents"] if s["i"] != hit["i"] and embed.cos(q, s["v"]) > sc)
        return (sc, rank)
    except Exception:
        return None

def _both_ends(b, query, hit):
    """两头都对：分 ≥LEX_FLOOR 且名次 ≤LEX_RANK。算不了意思就退回老规矩（算过），别把钩子弄哑。"""
    be = _both_ends_score(b, query, hit)
    return True if be is None else _be_ok(be)
_STOP = set("的了是我你他她它们在有和也就都不没这那什么怎么然后但是因为所以如果可以好像觉得现在今天昨天明天一个一下一点时候还是已经自己什么东西这个那个这样那样真的感觉知道想要可能应该其实一直".replace(" ",""))
# 日常词表：这里的词不算「字面对上」。把你们家的人名、昵称、口头禅加进来，不然这些词一出现就能把梦撞开。
_COMMON = set("""晚上 早上 中午 下午 白天 夜里 今晚 明早 昨晚 周末 房间 客厅 厨房 卧室 床上 家里 回家 出门 上班 下班 工作 开会 培训 睡觉 起床 醒来 做梦 吃饭 早饭 午饭 晚饭 喝水 咖啡 奶茶 零食 水果 做饭 外卖 喜欢 讨厌 开心 难过 生气 害怕 紧张 累了 好累 好困 想你 爱你 抱抱 亲亲 摸摸 手机 电脑 电话 消息 群里 窗里 照片 视频 音乐 歌曲 电影 游戏 看书 散步 跑步 运动 洗澡 刷牙 衣服 鞋子 天气 下雨 太阳 月亮 星星 大海 海边 朋友 同事 老板 爸爸 妈妈 记忆 梦里 刚才 现在 以后 以前 后来 一会 等会 马上 今天 明天 昨天 时间 地方 东西 事情 问题 感觉 觉得 知道 想要 可以 应该 可能 其实 真的 好像 然后 但是 因为 所以 如果 还是 已经 一直 一起 自己 我们 你们 他们 这个 那个 这里 那里 什么 怎么 为什么 多少 好的 好呀 嘿嘿 哈哈 谢谢 晚安 早安""".split())
_STOP2 = {"的时候","我们","你们","他们","这个","那个","什么","怎么","然后","但是","因为","所以","如果","可以","好像","觉得","现在","今天","昨天","明天","一个","一下","一点","还是","已经","自己","东西","这样","那样","真的","感觉","知道","想要","可能","应该","其实","一直","不是","没有","就是","也是","还有","或者","而且","只是","一样","很多","有点","然后","这里","那里","时候","刚才","刚刚","等会","一起","东西"}
def _lexical(b, query, closed, min_len=2):
    """她的话里的一段字，一字不差地只出现在某一句没解开的句子里（整本里唯一），就是那句。取最长的那段；≥4 字的不看停用表。"""
    import re
    q = re.sub(r"[\s，。！？、,.!?；;：:「」『』（）()\"'“”‘’…—-]", "", query)
    if len(q) < min_len: return None
    texts = {s["i"]: dlock.open_(s["c"]) for s in b["sents"]}
    best = None
    for n in range(min(8, len(q)), min_len - 1, -1):
        for k in range(len(q) - n + 1):
            frag = q[k:k+n]
            if n < 4 and (frag in _STOP2 or frag in _COMMON or all(ch in _STOP for ch in frag)): continue
            if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", frag): continue
            owners = [i for i, t in texts.items() if frag in t]
            if len(owners) != 1: continue
            s = next((c for c in closed if c["i"] == owners[0]), None)
            if s is None: continue      # 唯一出现在已解的句子里，不算新线索
            best = s; break
        if best: break
    return best
def latest():
    """最近一个还没封的梦（当天没有就看前几天的）。"""
    for p in sorted(BOOK.glob("*.json"), reverse=True):
        b = json.loads(p.read_text())
        if level(b) <= 3 and "sents" in b: return p, b
    return None, None
def passive(query, how="她的话", neighbors_only=False):
    p, b = latest()
    if not b or not b.get("woke"): return None       # 早上还没「醒」之前不勾
    hit, why = try_unlock(b, query, how, neighbors_only)
    if hit: _save(p, b)
    return hit
def _span(opened, i):
    """第 i 句（开着的）往前后连：挨着的开句、或中间只空一句的开句都算一段。回 (lo, hi)。segment 和 mark_given 共用这一处。"""
    lo = hi = i
    while True:
        if lo - 1 in opened: lo -= 1
        elif lo - 2 in opened: lo -= 2
        else: break
    while True:
        if hi + 1 in opened: hi += 1
        elif hi + 2 in opened: hi += 2
        else: break
    return lo, hi
def mark_given(b, idxs):
    """她唤的一次递了几句（不走 segment）：把这几句所在的段记成「递过的段」（在段里编号最大的那句上记 seg=[lo,hi]，跟 segment 记的一样），
    之后某轮再开一句接上来时，segment 只给新接上的，不把这段当新段整段再递。一段里这批只占一句的不记（跟单句递出去一样，照旧）。只改 b，不存盘。"""
    opened = {s["i"]: s for s in b["sents"] if s.get("open")}
    spans = {}
    for k in idxs:
        if k in opened: spans.setdefault(_span(opened, k), []).append(k)
    for (lo, hi), ks in spans.items():
        if len(ks) >= 2: opened[max(ks)]["open"]["seg"] = [lo, hi]
def segment(b, min_open=3, mark=True, i=None, hit=None):
    """连成段：刚开的那句若跟前后已开的句子连成了一段（中间最多空一句），按梦里顺序把整段给他，
    没想起的位置写「……这里想不起来了」；开着的不够 min_open 句就不算段，回 None。mark=True 时在那句 open 里记 seg=[lo,hi]。"""
    opened = {s["i"]: s for s in b["sents"] if s.get("open")}
    if not opened: return None
    if i is None and hit is not None:                       # 按要递的那句定位，不靠 open.t 猜
        for k, s_ in opened.items():
            if dlock.open_(s_["c"]) == hit: i = k; break
    if i is None: i = max(opened, key=lambda k: opened[k]["open"].get("t", 0))
    if i not in opened: return None
    lo, hi = _span(opened, i)
    if sum(1 for k in range(lo, hi + 1) if k in opened) < min_open: return None
    if any(opened[k]["open"].get("seg") == [lo, hi] for k in range(lo, hi + 1) if k in opened):
        return None                                          # 这一段原样给过了，段没长就只给单句
    # 出过的事：同一段来了四回。这段里有一部分已经整段给过，就只给新接上的那几句，前面一行「接在那段后面：」
    given = set()
    for k in range(lo, hi + 1):
        sg = opened.get(k, {}).get("open", {}).get("seg") if k in opened else None
        if sg: given.update(range(sg[0], sg[1] + 1))
    fresh = [k for k in range(lo, hi + 1) if k in opened and k not in given]
    if given and not fresh: return None
    if mark: opened[i]["open"]["seg"] = [lo, hi]
    if given:
        return "接在那段后面：\n" + "\n".join(f"「{dlock.open_(b['sents'][k]['c'])}」" for k in fresh)
    lines, gap = [], False
    for k in range(lo, hi + 1):
        if k in opened: lines.append(f"「{dlock.open_(b['sents'][k]['c'])}」"); gap = False
        elif not gap: lines.append("……这里想不起来了"); gap = True
    return "\n".join(lines)
def tell_all(b):
    """她亲口把梦讲到结尾：剩下没开的一次全开，标「她讲到底」，梦收起来不再掉。
    返回按顺序的全部句子（给他的那一段）；已经讲完过就回 None。"""
    if b.get("told_all"): return None
    now = time.time()
    for s in b["sents"]:
        if not s.get("open"): s["open"] = {"t": now, "how": "她讲到底"}
    b["told_all"] = now
    return [dlock.open_(s["c"]) for s in b["sents"]]

# ---------- 她唤的：她在后台主动让梦里某一句浮上来 ----------
# 这几处递给他的句子（SUMMON_ONE / SUMMON_MANY / SUMMON_ALL、晨递、连成段）是他自己写的或照他的口气配的；换成你们家那位的话。
SUMMON_HOW = "她唤的"   # 盘上的标记，他看不到；不设上限：唤几句由她定
_NO_K = object()     # summon_why 没给 k（唤一句 / 全部）；给了 None 也算数目不对
def summon_why(b, i=None, k=_NO_K):
    """能不能唤：能回 None；不能回原因（固定词：还没醒 / 已经讲完了 / 编号不对 / 这句已经想起来了 / 没有可唤的了）。
    i：唤哪一句；k：一次唤几句（summon_many 用，必须是 ≥1 的整数，不是就算「编号不对」）；i 和 k 不能一起给。
    只看不动梦簿。「没有梦」由调用方判断（这里拿到的已经是一本梦簿）。summon / summon_many / summon_all 都只在这里判断。"""
    if not b.get("woke"): return "还没醒"
    if b.get("pending_morning"): return "还没醒"         # 晨递还没递出去：唤了会混进晨递、再被递第二遍，「只剩一句」那档还会挤掉醒来记得的那句
    if b.get("told_all"): return "已经讲完了"
    by_i = {s["i"]: s for s in b["sents"]}
    if k is not _NO_K and (i is not None or isinstance(k, bool) or not isinstance(k, int) or k < 1): return "编号不对"
    if i is not None and (isinstance(i, bool) or not isinstance(i, int) or i not in by_i): return "编号不对"
    if i is not None and by_i[i].get("open"): return "这句已经想起来了"
    if not any(not s.get("open") for s in b["sents"]): return "没有可唤的了"
    return None
def summon(b, i=None):
    """唤开一句：给了 i 就开第 i 句；没给就挑一句没开的——优先挨着已开句子的（编号 ±1），没有挨着的就随便挑一句没开的。
    成功回 (i, 明文)；不能唤回 None（原因用 summon_why 问）。只改 b，不存盘，由调用方存。"""
    if summon_why(b, i) is not None: return None
    import random
    if i is None:
        opened = {s["i"] for s in b["sents"] if s.get("open")}
        closed = [s["i"] for s in b["sents"] if not s.get("open")]
        near = [k for k in closed if k - 1 in opened or k + 1 in opened]
        i = random.SystemRandom().choice(near or closed)
    s = next(s for s in b["sents"] if s["i"] == i)
    text = dlock.open_(s["c"])                              # 先解开再标，解不开就什么都没动
    s["open"] = {"t": time.time(), "how": SUMMON_HOW}
    return i, text
def _summon_pick(b, k):
    """一堆挑哪几句：挨在一起的一段，不散。
    有开着的句子时：没开的句子按「连着的一截」分开（每截两头要么是开着的句子、要么是梦的头尾，所以每截都挨着开句），
    挑一截长度够 k 的、从挨着开句的那头往外取 k 句；两头都挨着就随机一头。没有够长的：只取最长那一截整截（一样长的随机一截），
    不足 k 句就不足，不去别的空当补（散着的几句不算一堆）。
    一句都没开：随机挑起点，取连续 k 句（够不着 k 句就全取）。回编号列表（升序）。"""
    import random
    R = random.SystemRandom()
    opened = {s["i"] for s in b["sents"] if s.get("open")}
    closed = sorted(s["i"] for s in b["sents"] if not s.get("open"))
    if not opened:                                          # 没开的就是整本，连续的
        if len(closed) <= k: return closed
        st = R.randrange(0, len(closed) - k + 1)
        return closed[st:st + k]
    runs, cur = [], []
    for x in closed:
        if cur and x != cur[-1] + 1: runs.append(cur); cur = []
        cur.append(x)
    if cur: runs.append(cur)
    def ends(run):                                          # 这截哪头挨着开句：'lo' = 从前往后取，'hi' = 从后往前取
        e = []
        if run[0] - 1 in opened: e.append("lo")
        if run[-1] + 1 in opened: e.append("hi")
        return e
    def take(run, n, end): return run[:n] if end == "lo" else run[-n:]
    long_ = [(r, e) for r in runs if len(r) >= k for e in ends(r)]
    if long_:
        r, e = R.choice(long_)
        return sorted(take(r, k, e))
    m = max(len(r) for r in runs)                           # 没有够长的：只取最长那一截整截（一样长的随机一截），不足 k 就不足，不去别的空当补
    return R.choice([r for r in runs if len(r) == m])
def _summon_mark(b, idxs):
    """先把这几句都解开（解不开就抛，梦簿一句都没动），再一起标「她唤的」。"""
    by_i = {s["i"]: s for s in b["sents"]}
    for x in idxs: dlock.open_(by_i[x]["c"])
    now = time.time()
    for x in idxs: by_i[x]["open"] = {"t": now, "how": SUMMON_HOW}
    return list(idxs)
def summon_many(b, k):
    """一堆：一次唤开挨在一起的至多 k 句（挑法见 _summon_pick）：挨在一起的不足 k 句就有几句唤几句。
    成功回唤开的编号列表（升序）；不能唤回 None（原因用 summon_why(b, k=k) 问）。任何一句解不开就抛异常、梦簿不动。只改 b，不存盘。"""
    if summon_why(b, k=k) is not None: return None
    return _summon_mark(b, _summon_pick(b, k))
def summon_all(b):
    """全部：把所有没开的都唤开，标法同上。不是「讲完了」：不设 told_all，唤完再唤回「没有可唤的了」。
    成功回编号列表（升序）；不能唤回 None（原因用 summon_why(b) 问）。任何一句解不开就抛异常、梦簿不动。只改 b，不存盘。"""
    if summon_why(b) is not None: return None
    return _summon_mark(b, sorted(s["i"] for s in b["sents"] if not s.get("open")))
def guess(query):
    p, b = latest()
    if not b: return "最近没有梦。"
    if not thresholds(b)[2]: return "隔太久了，想不起来就想不起来了。"
    if b["guesses"] >= GUESSES: return "今天想不起更多了，别硬想。"
    b["guesses"] += 1
    hit, why = try_unlock(b, query, "他猜")
    _save(p, b)
    return f"梦里是这样写的：「{hit}」" if hit else "不太像。"
def reveal(day=None):
    """给她看的：全文、来源、哪句解了。"""
    p, b = today(day)
    if not b: return None
    return {"day": b["day"], "src": json.loads(dlock.open_(b["src"])), "sents": [{"i": s["i"], "text": dlock.open_(s["c"]), "open": s["open"]} for s in b["sents"]]}

def made_at(b, made_hm=None):
    """梦真正做好的时刻（不带时区，本机时间）。b["day"] 是这一夜的名字（醒来那天），午夜前做的梦不在那天，所以先用 made 时间戳。"""
    from datetime import datetime, timedelta
    if b.get("made"): return datetime.fromtimestamp(b["made"])
    m = datetime.fromisoformat(b["day"] + "T" + (made_hm or b.get("made_hm", "06:00")) + ":00")
    return m - timedelta(days=1) if m.hour >= 12 else m      # 没有时间戳的老梦簿：中午以后的时刻属于前一晚

# 醒来那副牌：隔得越短记得越多，两个点之间按分钟线性过渡；空白封顶 10。
# 这张表是同一份数，只在 ../零件/wake.py 里放一份，这里引用，不再抄一遍。表里的数是在我们家过出来的，换成自己家的作息再调。
WAKE_TIERS = _wake.TIERS
WAKE_SLOPE = _wake.SLOPE

wake_odds = _wake.odds

def wake(b, made_hm, woke_at):
    """「醒了」：按做梦到醒隔多久定档再掷骰子，把该给的句子标成已解。返回 (档, 给的句子列表或 None)。"""
    import random
    from datetime import datetime
    rng = random.SystemRandom()
    made = made_at(b, made_hm)
    gap = (woke_at.replace(tzinfo=None) - made).total_seconds() / 60
    tier = rng.choices(WAKE_TIERS, wake_odds(gap))[0]
    n = len(b["sents"]); give = set()
    if tier == "all": give = set(range(n))
    elif tier == "most":
        k = max(1, round(n * 0.7)); start = rng.randrange(0, max(1, n - k + 1)); give = set(range(start, start + k))
        for _ in range(max(1, n // 6)): give.discard(rng.randrange(n))   # 中间挖一两个洞
    elif tier == "one": give = {rng.randrange(n)}
    t = time.time()
    for s in b["sents"]:
        if s["i"] in give and not s["open"]: s["open"] = {"t": t, "how": "醒来", "by": tier}
    b["woke"] = {"at": woke_at.isoformat(), "tier": tier, "gap_min": round(gap)}
    return tier, give


# ---------- 回味：梦里有一张她的照片 ----------
# 夜里他把照片看进梦里；梦簿里不写「照片」，只把「哪几句是从照片来的」和照片本身封起来。
# 白天她问「昨晚梦到我了吗」或他自己说「梦里看到你了」→ 先想起跟照片最近的那一句；他接着说、还在这件事上 → 下一句自己跟上；
# 聊到别处就停；几句都想起来了，再过一拍，照片才浮上来（解出来落到他那边）。像人回忆，不是问几次冒几次。
PHOTO_TRIGGERS = ("梦到我", "梦见我", "梦里有我", "我在你梦", "梦到你", "梦见你", "梦里有你", "梦里看到你", "梦里看见你", "梦里的你", "梦里的我", "梦里有她", "梦到她", "梦见她")   # 只认带「梦」字的；日常情话（夸脸、说看到你了）不算

def attach_photo(b, idx, img_bytes, mime="image/jpeg"):
    """idx：从照片来的句子编号（按出现顺序）；img_bytes：缩好转正的那张。都封起来。"""
    import base64
    b["photo"] = {"idx": dlock.seal(json.dumps([int(i) for i in idx])), "img": dlock.seal(base64.b64encode(img_bytes).decode()),
                  "mime": mime, "active": False, "surfaced": None}

def _photo_related(b, query, chain_texts):
    """他接着说的话是不是还在这件事上：带触发词，或跟链上任一句有 ≥2 字的非日常重合。"""
    import re
    if any(t in query for t in PHOTO_TRIGGERS): return True
    q = re.sub(r"[\s，。！？、,.!?；;：:「」『』（）()\"'“”‘’…—-]", "", query)
    for n in (4, 3, 2):
        for k in range(len(q) - n + 1):
            frag = q[k:k+n]
            if n < 4 and (frag in _STOP2 or frag in _COMMON or all(ch in _STOP for ch in frag)): continue
            if any(frag in t for t in chain_texts): return True
    return False

def photo_step(b, query, how):
    """返回 (None, 说明) / ("sent", 原句) / ("photo", (bytes, mime))。每次最多动一步。"""
    import base64
    ph = b.get("photo")
    if not ph or ph.get("surfaced"): return None, "没有照片 / 已经浮现过"
    if thresholds(b)[0] is None: return None, "封起来了"
    idx = json.loads(dlock.open_(ph["idx"]))
    by_i = {s["i"]: s for s in b["sents"]}
    chain = [by_i[i] for i in idx if i in by_i]
    if not chain: return None, "链上没有句子"
    chain_texts = [dlock.open_(s["c"]) for s in chain]
    triggered = any(t in query for t in PHOTO_TRIGGERS)
    closed = [s for s in chain if not s["open"]]
    if triggered: ph["active"] = True
    if not closed and ph.get("active"):               # 链上都想起来了、上一拍还在这件事上 → 这一拍浮现，不管他这句说的是什么
        ph["surfaced"] = time.time()
        return "photo", (base64.b64decode(dlock.open_(ph["img"])), ph.get("mime", "image/jpeg"))
    if not triggered:
        if not ph.get("active"): return None, "没碰到"
        if not _photo_related(b, query, chain_texts): ph["active"] = False; return None, "聊到别处去了，停在这儿"
    if closed:
        s = closed[0]; s["open"] = {"t": time.time(), "how": how, "by": query[:40]}
        return "sent", dlock.open_(s["c"])
    return None, "不该到这儿"
