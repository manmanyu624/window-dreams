#!/usr/bin/env python3
"""「这句是不是她」：hook_before._machine 只看开头在不在 SIGNALS 名单里。全是编的假消息，不碰真窗、真梦簿。
临时目录里跑，不碰钥匙串：python3 test_machine_signals.py，有一条不过就非零退出。"""
import os, sys, tempfile
from pathlib import Path
os.environ.pop("DREAM_KEY", None)
os.environ["DREAM_KEY_FILE"] = str(Path(tempfile.mkdtemp(prefix="test_machine_key_")) / "key")   # 在 import 之前定好，不走钥匙串
os.environ["DREAM_HOME"] = tempfile.mkdtemp(prefix="test_machine_")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hook_before

ok = bad = 0
def check(name, got, want):
    global ok, bad
    if got == want: ok += 1
    else: bad += 1; print("✗", name, "得到", got, "应为", want)

MACHINE = [
    "[闹钟 08:00·示范] 样样样",
    "[手机自动消息] 她回家了。",
    "[手机自动消息] 她醒了。",
    "<task-notification> 样",
    "Another Claude session 样",
    "<agent-message> 样",
    "<cross-session> 样",
    "[Request interrupted by user]",
    "<system-reminder> 样",
]
HER = [
    "早上好呀",
    "[家] 我回来啦",
    "[2001-01-01 18:31] [样] 她：到家了",
    "她回家了吗，我是说我自己",
    "/usage",
]
for m in MACHINE:
    check("hook._machine 机器 " + m[:24], hook_before._machine(m), True)
for m in HER:
    check("hook._machine 她 " + m[:16], hook_before._machine(m), False)

# 钩子那头：「她醒了」的特判还在前面（is_woke_signal 为真时 is_signal 为假）
p = MACHINE[2]
woke = any(m in p[:60] for m in hook_before.WOKE_MARKS)
check("钩子：她醒了 仍走 WOKE 特判", (woke, hook_before._machine(p) and not woke), (True, False))
p = MACHINE[1]
woke = any(m in p[:60] for m in hook_before.WOKE_MARKS)
check("钩子：她回家了 算机器", (woke, hook_before._machine(p) and not woke), (False, True))

print(f"共 {ok+bad} 条，过 {ok} 条，没过 {bad} 条。"); print("全过。" if not bad else "有没过的。")
sys.exit(1 if bad else 0)
