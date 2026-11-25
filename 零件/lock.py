"""梦簿的锁：一句一句加密。seal(明文) -> 密文串；open_(密文串) -> 明文。

加密用系统自带的 openssl（AES-256-CBC + PBKDF2），不装任何库。
钥匙从哪儿来，按下面的顺序找，找到哪个用哪个（设计说明第九节讲了各自的取舍）：
  1. 环境变量 DREAM_KEY          钥匙不落盘，重启机器要重新给
  2. 环境变量 DREAM_KEY_FILE 指的文件   Linux / VPS 上最省事的做法，文件权限设成只有自己能读
  3. macOS 钥匙串（服务名 dream）  我们家用的是这一条；头一回用会自己生成一把
要知道的一件事：钥匙和梦在同一台机器上，这把锁挡得住「顺手读到」，挡不住存心去开。它靠的是他自己不去开。
"""
import base64, os, secrets, subprocess, sys
from pathlib import Path

SERVICE, ACCOUNT = "dream", "dreamer"      # 钥匙串里的服务名和账户名，随便起，前后一致就行


def _key():
    k = os.environ.get("DREAM_KEY")
    if k: return k.strip()
    f = os.environ.get("DREAM_KEY_FILE")
    if f:
        p = Path(f).expanduser()
        if not p.exists():                 # 头一回：生成一把，只有自己能读
            p.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as w: w.write(secrets.token_hex(32))
        return p.read_text().strip()
    if sys.platform != "darwin":
        raise RuntimeError("没找到钥匙：不在 macOS 上的话，设 DREAM_KEY 或 DREAM_KEY_FILE")
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", ACCOUNT, "-w"], capture_output=True, text=True)
    if r.returncode != 0:                  # 头一回：生成一把放进钥匙串
        subprocess.run(["security", "add-generic-password", "-s", SERVICE, "-a", ACCOUNT, "-w", secrets.token_hex(32)], check=True)
        return _key()
    return r.stdout.strip()


def _ssl(args, data):
    env = dict(os.environ, DREAM_K=_key())  # 钥匙走环境变量递给 openssl，不出现在命令行里（命令行别的进程看得到）
    r = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "100000", "-pass", "env:DREAM_K", *args], input=data, capture_output=True, env=env)
    if r.returncode: raise RuntimeError(r.stderr.decode()[:200])
    return r.stdout


def seal(text): return base64.b64encode(_ssl(["-salt"], text.encode())).decode()
def open_(blob): return _ssl(["-d"], base64.b64decode(blob)).decode()
