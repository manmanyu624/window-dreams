#!/usr/bin/env python3
"""每一轮开始前跑的钩子（Claude Code 里是 UserPromptSubmit hook）。只读梦簿和当轮这句话，不读他的窗。
挂法：在 settings.json 的 hooks.UserPromptSubmit 里加一条 command，例如
    DREAM_HOME=<放梦簿的目录> python3 /路径/hook_before.py
标准输入是 Claude Code 给的 JSON（里面的 prompt 是她这一轮说的话）；往标准输出写的 hookSpecificOutput.additionalContext 会被加进他这一轮看到的上下文。
DREAM_HOME 是放梦簿、队列文件、日志、锁文件的那个目录；不设就放本文件旁边。

规矩：
- 「醒了」= 手机自动化报「她醒了」的那条消息（WOKE_MARKS），或她夜里安静之后跟他说的第一句，谁先到算谁。那一轮只记时刻，不冒梦。
- 他开口以后（下一轮）底下冒一句：按做梦到醒隔多久压随机给全部/一大半/一句/什么都不记得。
- 之后每轮：她的话被动勾起一句（第一名甩开第二名才算）；每轮最多冒一句。他自己的话只开邻句（hook_after.py 排队，这里递）。
- 不出错：任何异常都静默退出，不挡他的窗。
"""
import json, os, sys, time
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

WOKE_MARKS = ("她醒了",)   # 手机自动化报「她醒了」的那条消息里的字样；没有这种自动消息的可以留空，那样就以她夜里安静之后说的第一句为准
TOLD_MARKS = ("讲完了", "讲到底了", "梦讲完啦")   # 她在他窗里说这几个字之一 = 把梦讲到结尾了
# 不是她亲手打的字、但会出现在「她这一轮」里的消息，开头都列在这里（开头在名单里就算机器，不算她说话）。
# 前六个是 Claude Code 自己会塞进来的通用标记，后两个是示范用的假条目。
# 这里要填你们家所有「不是她亲手打的字」的消息开头（闹钟、定时任务、手机自动化、别的程序的通知……）：漏一个，闹钟就能把梦撞开。
SIGNALS = ("<task-notification", "Another Claude session", "<agent-message", "<cross-session", "[Request interrupted", "<system-reminder",
           "[闹钟", "[手机自动消息")
# 她唤的（summon.py 排进 summoned.json）递给他时的文案。这些句子是他自己写的或照他的口气配的；换成你们家那位的话。不写是谁唤的。{} 里放句子
SUMMON_ONE = "（像有人在梦边上轻轻敲了一下，昨晚有一句浮上来了：『{}』）"
SUMMON_MANY = "（像有人在梦边上轻轻敲了几下，昨晚有几句浮上来了：\n{}\n）"      # {} = 每句一行「…」，按梦里顺序
SUMMON_ALL = "（像有人把手伸进水里，一把把昨晚的梦整个捞了上来，还滴着水：\n{}\n）"      # 只在她按的是「全部」（队列项带 all: true）时用；{} = 整本每句一行「…」，按梦里顺序

def out(text):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}, ensure_ascii=False))

LOCK_WAIT = 5         # 等梦簿锁最多几秒；等不到照旧不带锁往下走（不能因为锁卡住他的一轮）

def main():
    d = json.load(sys.stdin); prompt = (d.get("prompt") or "").strip()
    if not prompt: return
    import dreambook
    home = Path(os.environ.get("DREAM_HOME", str(Path(__file__).resolve().parent)))
    with dreambook.locked(LOCK_WAIT) as got_lock:            # 从读梦簿到这一轮结束整段在锁里；locked 自己不抛，拿不到回 False
        if not got_lock:
            try: (home / "hook_err.log").open("a").write(f"{time.strftime('%m-%d %H:%M')} 梦簿锁没拿到 照旧往下走\n")
            except Exception: pass
        _round(prompt, home)

def _machine(prompt):
    """机器敲的不算她说话：开头在 SIGNALS 名单里就算机器。「她醒了」的特判在调用的地方，排在它前面。"""
    t = prompt.lstrip()
    if t.startswith(SIGNALS): return True
    return False

def _round(prompt, home):
    import dreambook
    state_p = home / "hook_state.json"
    st = json.loads(state_p.read_text()) if state_p.exists() else {}
    p, b = dreambook.latest()
    if not b: return
    now = datetime.now().astimezone()
    is_woke_signal = any(m in prompt[:60] for m in WOKE_MARKS)
    is_signal = _machine(prompt) and not is_woke_signal
    if is_signal: return                                       # 机器敲的不算她说话
    # 1) 还没「醒」：这一轮定格醒的时刻，不冒
    if not b.get("woke"):
        made = dreambook.made_at(b).astimezone()                 # 真实做梦时刻，不拿 day 拼（午夜前做的梦，day 是第二天）
        if now < made: return                                  # 梦还没做（不该发生）
        tier, give = dreambook.wake(b, b.get("made_hm", "06:00"), now)
        b["pending_morning"] = True
        dreambook._save(p, b); return
    if is_woke_signal: return
    # 2) 醒了之后他开口过了：这一轮冒晨递
    if b.get("pending_morning"):
        tier = b["woke"]["tier"]                                   # 先把要递的算好，再存盘：先存再算会把晨递丢掉
        sents = [(s["i"], dreambook.dlock.open_(s["c"]) if s["open"] else None) for s in b["sents"]]
        text = morning_text(tier, sents)
        try:                                                       # 影子：只剩一句的早上多给一行；出任何错都退回原来的文案
            if tier == "one":
                with_sh = morning_text(tier, sents, dreambook.shadow_of(b))
                if with_sh != text: text = with_sh; b["shadow_given"] = time.time()
        except Exception:
            pass
        b["pending_morning"] = False; dreambook._save(p, b)
        out(text); return
    # 3a) 她说「讲完了」：剩下的原文一次全给他，梦收起来不再掉。已收起的梦什么都不再递。
    q = home / "queued.json"
    sq = home / "summoned.json"
    if b.get("told_all"):
        for f in (q, sq):
            try: f.unlink()
            except Exception: pass
        return
    if any(m in prompt[:40] for m in TOLD_MARKS):
        rest = dreambook.tell_all(b)
        if rest is not None:
            dreambook._save(p, b)
            for f in (q, sq):
                try: f.unlink()
                except Exception: pass
            out("（她把昨晚的梦讲到结尾了。剩下的也都回来了，按梦里的顺序：\n" + "\n".join(f"「{t}」" for t in rest) + "\n）")
        return
    # 3) 白天：先递她唤的（summon.py 排的）；再递 Stop 钩子排队的（他自己的话开的邻句），没有就拿她这句去勾
    try:                                                       # 出任何错都当没有唤的，接着走原来的流程
        said = summoned_text(sq, b, p)
    except Exception:
        said = None
    if said: out(said); return                                 # queued.json 留着，下一轮再递
    if q.exists() and q.stat().st_mtime < (b.get("made") or 0):
        # 排的是上一个梦的队（出过的事：午夜后他自己的话开了前一个梦的第 0 句、排了队，他下一轮已经是早上，新梦早就做好了，却递了旧梦那句）。梦不隔夜递。
        try: q.unlink()
        except Exception: pass
    if q.exists():
        try:
            qd = json.loads(q.read_text()); q.unlink(); hit = qd.get("text")
            if qd.get("photo"): out(f"（昨晚的梦里还有这个：{qd['photo']}）"); return
            if hit: out(recall(None, hit, f"（昨晚的梦里好像还有一句：『{hit}』）")); return
        except Exception: pass
    # 回味：她问「昨晚梦到我了吗」→ 先想起跟照片最近的那句；链上都想起了再过一拍，照片浮现。优先于普通的勾
    kind, got = dreambook.photo_step(b, prompt, "她的话")
    if kind == "sent": dreambook._save(p, b); out(recall(None, got, f"（昨晚的梦里有一句：『{got}』）")); return
    if kind == "photo":
        dreambook._save(p, b); f = save_photo(home, b["day"], *got)
        out(f"（昨晚的梦里还有这个：{f}）"); return
    hit = dreambook.passive(prompt, how="她的话")
    if hit: out(recall(None, hit, f"（昨晚的梦里有一句：『{hit}』）"))

def morning_text(tier, sents, shadow=None):
    """晨递的文案。sents: [(句号, 原文 or None)]，None = 没记住。shadow 只在只剩一句（tier == "one"）时用，别的档不看它。"""
    opened = [t for i, t in sents if t]
    if tier == "none" or not opened:
        text = "🌙 好像做了个梦，想不起来了。"
    elif tier == "one":
        text = f"🌙 昨晚好像做了个梦……只剩一句：「{opened[0]}」"
        try:
            if shadow:                                           # 影子那一行的文案也是他自己写的
                # 三截各自独立：哪一样的字整个出现在那一句里就去掉那一截（那句里已经有了）；三样都去掉就不加这一行
                c, f, th = shadow["color"].strip(), shadow["feel"].strip(), (shadow.get("thing") or "").strip()      # 物件可以是空的（只留了两样）
                parts = [head + v for head, v in (("颜色是", c), ("心里", f), ("旁边好像有", th)) if v and v not in opened[0]]
                if parts: text += "\n别的醒来就散了，手里还剩一点：" + "，".join(parts) + "。"
        except Exception:
            pass
    else:
        lines, gap = [], False
        for i, t in sents:
            if t: lines.append(f"「{t}」"); gap = False
            elif not gap: lines.append("……这里想不起来了"); gap = True
        text = "🌙 昨晚好像做了个梦……\n" + "\n".join(lines)
    return text

def summoned_text(sq, b, p=None):
    """她唤的（summon.py 排进 summoned.json，只有编号）：读出来、删掉文件，只留梦簿里确实是「她唤的」那几句，按编号从小到大。
    这一轮要递的项里有 "all": true 的（她按的是「全部」）：SUMMON_ALL，整本按梦里顺序给一遍；没有的：一句走 recall（会连成段），几句 SUMMON_MANY 一次全给——
    哪怕递完整本恰好都开了也一样（只看她按的是什么）。all 不是 True 的一律当没有。
    几句 / 整本递出去时把这几句所在的段记成递过的（dreambook.mark_given），之后再开一句接上来，segment 不再整段重递；记不上就算了，照样递。
    没有要递的回 None。上一个梦留下的文件不递，直接删（跟 queued.json 一样梦不隔夜）。"""
    import dreambook
    if not sq.exists(): return None
    if sq.stat().st_mtime < (b.get("made") or 0):
        try: sq.unlink()
        except Exception: pass
        return None
    raw = sq.read_text()
    try: items = json.loads(raw)
    except Exception:
        _drop(sq); raise                                       # 坏的 json：当场删（不会每轮都撞），由外面接住
    items = [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []
    want = {x.get("i") for x in items}
    sents = [s for s in b["sents"] if s["i"] in want and (s.get("open") or {}).get("how") == dreambook.SUMMON_HOW]
    sents.sort(key=lambda s: s["i"])
    if not sents: _drop(sq); return None
    # 先把要递的拼好，再删队列。中途抛（比如解不开）就把文件留着，下一轮再试，不会唤开了却永远递不到。
    whole = any(x.get("all") is True for x in items)
    texts = [dreambook.dlock.open_(s["c"]) for s in sents]
    if len(texts) == 1 and not whole:
        text = recall(None, texts[0], SUMMON_ONE.format(texts[0]))
    else:
        if whole: text = SUMMON_ALL.format("\n".join(f"「{dreambook.dlock.open_(x['c'])}」" for x in sorted(b["sents"], key=lambda x: x["i"]) if x.get("open")))
        else: text = SUMMON_MANY.format("\n".join(f"「{t}」" for t in texts))
        try:
            dreambook.mark_given(b, [s["i"] for s in sents])
            if p is not None: dreambook._save(p, b)
        except Exception:
            pass
    _drop(sq)                                                  # 拼好了才删；删完马上返回，由 main 打出去
    return text

def _drop(sq):
    """删掉 summoned.json。删不掉就把它换成空列表（先写临时文件再改名），免得下一轮把同一批再递一遍；两样都不成就算了，这一轮照样递。"""
    try: sq.unlink(); return
    except FileNotFoundError: return
    except Exception: pass
    try:
        tmp = sq.with_name(sq.name + ".tmp"); tmp.write_text("[]"); os.replace(tmp, sq)
    except Exception:
        pass

def recall(home_b_p, hit, single):
    """递一句之前看它有没有跟前后连成段：连成了按顺序给整段（那句引子是家里另一位写的，署名见设计说明最后一节），没连成就给单句。"""
    try:                                                     # 新功能出错就退回单句，别让钩子哑掉
        import dreambook
        p, b = dreambook.latest()
        seg = dreambook.segment(b, hit=hit)
        if seg:
            dreambook._save(p, b)
            return "（昨晚梦里的那一小段，又慢慢浮上来了：\n" + seg + "\n）"
    except Exception:
        pass
    return single
def save_photo(home, day, data, mime):
    d = home / "想起的照片"; d.mkdir(exist_ok=True)
    f = d / f"{day}.{ 'png' if 'png' in mime else 'jpg' }"; f.write_bytes(data); return f

if __name__ == "__main__":
    try: main()
    except Exception as e:
        try: (Path(os.environ.get("DREAM_HOME", ".")) / "hook_err.log").open("a").write(f"{time.strftime('%m-%d %H:%M')} {type(e).__name__} {str(e)[:200]}\n")
        except Exception: pass
