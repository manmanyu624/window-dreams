#!/usr/bin/env python3
"""她唤的：她那一页的后台调这个，让梦里的句子浮上来。
  python3 summon.py            唤一句（挑挨着已开的）
  python3 summon.py --i N      唤第 N 句（也认 --i=N）
  python3 summon.py --n K      唤一堆：挨在一起的 K 句（也认 --n=K；挨在一起的不足 K 句就有几句唤几句，不去别处凑）
  python3 summon.py --all      唤全部没开的（不是「讲完了」）
--i / --n / --all 只能用一个。开了就存梦簿，并把编号排进 home/summoned.json（只记编号不记明文；--all 那批每项多记 "all": true，
钩子见到它才用整本的文案），下一轮由 hook_before 递给他。
标准输出只打一行 json：
  单句（不带参数 / --i）成功 {"ok": true, "i": N}；一堆 / 全部成功 {"ok": true, "i": [编号…升序], "n": 条数}；
  不成 {"ok": false, "why": 固定词}。任何情况下都不打印句子的明文，退出码总是 0。"""
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

LOCK_WAIT = 10        # 等梦簿锁最多几秒（网页后台调，可以多等一会儿）

def home():
    return Path(os.environ.get("DREAM_HOME", str(Path(__file__).resolve().parent)))

def parse(argv):
    """回 (ok, 方式, 值)。方式：'one'（值 = 编号或 None）/ 'many'（值 = K）/ 'all'（值 None）。
    只认：什么都不带 / --i N / --i=N / --n K / --n=K / --all；别的样子（混用、多给、缺值、不是数）都算编号不对。"""
    if not argv: return True, "one", None
    if argv == ["--all"]: return True, "all", None
    for flag, mode in (("--i", "one"), ("--n", "many")):
        if len(argv) == 1 and argv[0].startswith(flag + "="): v = argv[0][len(flag) + 1:]
        elif len(argv) == 2 and argv[0] == flag: v = argv[1]
        else: continue
        try: return True, mode, int(v.strip())
        except Exception: return False, None, None
    return False, None, None

def enqueue(q, idxs, made, all_=False):
    """追加 {"i", "at"}（每个编号一项；all_ 时每项再加 "all": true）到 summoned.json：先写临时文件再 os.replace。
    读不出来的旧文件、上一个梦留下的项都丢掉；留下的旧项原样留着（包括它的 all 键）。"""
    if isinstance(idxs, int): idxs = [idxs]
    items = []
    if q.exists():
        try:
            old = json.loads(q.read_text())
            if isinstance(old, list):
                items = [x for x in old if isinstance(x, dict) and isinstance(x.get("i"), int) and (x.get("at") or 0) >= made]
        except Exception:
            items = []
    now = time.time()
    items += [dict({"i": i, "at": now}, **({"all": True} if all_ else {})) for i in idxs]
    tmp = q.with_name(q.name + ".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False))
    os.replace(tmp, q)

def run(argv):
    good, mode, v = parse(argv)
    if not good: return {"ok": False, "why": "编号不对"}
    import dreambook
    with dreambook.locked(LOCK_WAIT) as got_lock:         # 从读梦簿到排完队整段在锁里；等不到锁就什么都不动
        if not got_lock: return {"ok": False, "why": "出错了"}
        return _run_locked(dreambook, mode, v)

def _run_locked(dreambook, mode, v):
    p, b = dreambook.latest()
    if not b: return {"ok": False, "why": "没有梦"}
    why = dreambook.summon_why(b, i=v) if mode == "one" else dreambook.summon_why(b, k=v) if mode == "many" else dreambook.summon_why(b)
    if why: return {"ok": False, "why": why}
    if mode == "one":
        got = dreambook.summon(b, v)
        if not got: return {"ok": False, "why": "出错了"}
        idxs = [got[0]]                              # 明文不出这个函数
    else:
        idxs = dreambook.summon_many(b, v) if mode == "many" else dreambook.summon_all(b)
        if not idxs: return {"ok": False, "why": "出错了"}
    dreambook._save(p, b)
    try:
        enqueue(home() / "summoned.json", idxs, b.get("made") or 0, all_=(mode == "all"))
    except Exception:
        # 排不进队：把这批都关回去，别让它们开了却永远递不到
        try:
            for s in b["sents"]:
                if s["i"] in idxs and (s.get("open") or {}).get("how") == dreambook.SUMMON_HOW: s["open"] = None
            dreambook._save(p, b)
        except Exception:
            pass
        return {"ok": False, "why": "出错了"}
    if mode == "one": return {"ok": True, "i": idxs[0]}
    return {"ok": True, "i": sorted(idxs), "n": len(idxs)}

def main(argv=None):
    try: res = run(sys.argv[1:] if argv is None else argv)
    except Exception: res = {"ok": False, "why": "出错了"}
    print(json.dumps(res, ensure_ascii=False))

if __name__ == "__main__":
    try: main()
    except Exception: pass
    sys.exit(0)
