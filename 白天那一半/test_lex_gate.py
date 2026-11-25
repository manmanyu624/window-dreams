#!/usr/bin/env python3
"""两头都对的那道门。只测 _be_ok 这张判定表，用日志里回放出来的分数和名次，不碰梦。
临时目录里跑，不碰钥匙串：python3 test_lex_gate.py，有一条不过就非零退出。"""
import os, sys, tempfile
from pathlib import Path
os.environ.pop("DREAM_KEY", None)
os.environ["DREAM_KEY_FILE"] = str(Path(tempfile.mkdtemp(prefix="test_lex_key_")) / "key")   # 在 import 之前定好，不走钥匙串
os.environ["DREAM_HOME"] = tempfile.mkdtemp(prefix="test_lex_")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dreambook as d
cases = [
    # (分, 名次, 该不该开, 说明)
    (0.58, 1, True, "老规矩本来就开"), (0.60, 2, True, "真对上的例子 1"), (0.68, 1, True, "真对上的例子 2"), (0.79, 1, True, "真对上的例子 3"), (0.62, 1, True, "真对上的例子 4"),
    (0.54, 2, True, "新：前三"), (0.52, 2, True, "新：前三"), (0.51, 3, True, "新：前三"), (0.50, 1, True, "新：前三"), (0.49, 3, True, "新：前三"), (0.43, 3, True, "新：前三"),
    (0.40, 3, True, "边界：正好 .40 第 3"), (0.39, 1, False, "分太低，名次第一也不开"), (0.54, 4, False, "第 4 名、分不到 .55"),
    (0.55, 5, True, "老规矩边界"), (0.59, 8, False, "没放宽到前十那条"), (0.58, 6, False, "同上"), (0.56, 9, False, "同上"),
    (0.45, 57, False, "不是"), (0.49, 31, False, "起来"), (0.53, 16, False, "想把"),
]
bad = [(c) for c in cases if d._be_ok((c[0], c[1])) != c[2]]
for c in bad: print("✗", c)
print(f"共 {len(cases)} 条，过 {len(cases)-len(bad)} 条，没过 {len(bad)} 条。"); print("全过。" if not bad else "有没过的。")
sys.exit(1 if bad else 0)
