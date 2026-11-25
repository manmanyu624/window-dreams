#!/usr/bin/env python3
"""他说完一轮以后跑的钩子（Claude Code 里是 Stop hook）：拿他这一轮的话，只去碰已解句旁边的（他自己的话只能勾出挨着的，开不了新块）。
挂法：在 settings.json 的 hooks.Stop 里加一条 command，例如
    DREAM_HOME=<放梦簿的目录> python3 /路径/hook_after.py
标准输入是 Claude Code 给的 JSON，里面的 transcript_path 指向这扇窗的记录，从末尾读出他刚说的这一轮。
对上了排进 queued.json，下一轮由 hook_before.py 递出去（做不到当场）。只读他这一轮的正文，不存、不打印。"""
import json, os, sys
LOCK_WAIT = 5         # 等梦簿锁最多几秒；等不到照旧不带锁往下走（跟 hook_before 一样，不能卡住他）
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

def last_assistant_text(transcript):
    txt = None
    for line in Path(transcript).read_text(encoding="utf-8", errors="replace").splitlines()[-200:]:
        try: r = json.loads(line)
        except ValueError: continue
        if r.get("type") != "assistant": continue
        c = (r.get("message") or {}).get("content")
        if isinstance(c, list):
            t = "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text").strip()
            if t: txt = t
    return txt

def main():
    d = json.load(sys.stdin)
    if d.get("stop_hook_active"): return
    home = Path(os.environ.get("DREAM_HOME", str(Path(__file__).resolve().parent)))
    import dreambook
    with dreambook.locked(LOCK_WAIT):                          # 读梦簿→改→存 / 写 queued.json 整段在锁里；拿不到照旧走。这里本来就不记日志
        _round(d, home)

def _round(d, home):
    import dreambook
    p, b = dreambook.latest()
    if not b or not b.get("woke") or b.get("pending_morning") or b.get("told_all"): return   # told_all：她讲完了，收起来
    t = last_assistant_text(d.get("transcript_path", ""))
    if not t: return
    # 回味：他自己说「梦里看到你了」或接着往下说 → 链上下一句跟上；都想起了再过一拍照片浮现
    kind, got = dreambook.photo_step(b, t[-600:], "他自己的话")
    if kind == "sent":
        dreambook._save(p, b); (home / "queued.json").write_text(json.dumps({"text": got}, ensure_ascii=False)); return
    if kind == "photo":
        dreambook._save(p, b)
        d = home / "想起的照片"; d.mkdir(exist_ok=True)
        f = d / f"{b['day']}.{'png' if 'png' in got[1] else 'jpg'}"; f.write_bytes(got[0])
        (home / "queued.json").write_text(json.dumps({"text": None, "photo": str(f)}, ensure_ascii=False)); return
    hit = dreambook.passive(t[-600:], how="他自己的话", neighbors_only=True)
    if hit: (home / "queued.json").write_text(json.dumps({"text": hit}, ensure_ascii=False))

if __name__ == "__main__":
    try: main()
    except Exception: pass
