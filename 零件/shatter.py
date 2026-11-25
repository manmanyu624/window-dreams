"""打碎：把今晚的几样料各剪一小块，交给一个小模型打成不讲道理的碎片。

为什么要打碎：直接把「今天发生了什么」递给他，出来的是今天的读后感。梦里的东西得是歪的。
碎片只是起头，递给他的时候不标哪片从哪儿来。
提示词里故意不出现「梦」字：小模型一看到这个字就开始写它以为的梦。
我们家用本机 ollama 里的 qwen3:8b；换模型只改 _ask()。
"""
import json, os, random, urllib.request

OLLAMA = os.environ.get("DREAM_OLLAMA", "http://127.0.0.1:11434")
MODEL = os.environ.get("DREAM_SMALL_MODEL", "qwen3:8b")

PROMPT = """下面是几段互不相关的文字。把它们全部打碎：每段只取一两处零碎的词或短语（三到八个字），不要完整的句子，不要解释，不要标来源，不要补充任何新内容。把碎片里的东西弄歪：数字改成差不多但不对的；地名换成熟悉但不对的；要是有人，换掉其中一个；原句里的话不要原样抄。其中一片把一件本来确定的事写成另一个样子，写得很肯定。把所有碎片打乱顺序，一行一个，总共 {n} 行。只输出碎片。

{body}"""


def _ask(prompt, temperature):
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=json.dumps({"model": MODEL, "prompt": prompt, "stream": False, "think": False, "options": {"temperature": temperature}}).encode(), headers={"Content-Type": "application/json"})
    for attempt in (1, 2):                 # 夜里撞上别的程序也在用同一个本机模型时超时过；失败再试一次
        try:
            with urllib.request.urlopen(req, timeout=300) as r: return json.load(r)["response"]
        except (TimeoutError, OSError):
            if attempt == 2: raise


def clean(raw, n):
    """把模型的回话收拾成碎片：去掉行首的编号和小圆点，太短太长的不要，最多 n 片。"""
    frags = [l.strip(" -•·0123456789.、") for l in raw.splitlines() if l.strip()]
    return [f for f in frags if 2 <= len(f) <= 20][:n]


def shatter(pieces, n=12, temperature=1.1):
    """pieces: [(来源标记, 文本), ...]。来源只用来洗牌，不进提示词。回 n 片以内的碎片，顺序是乱的。"""
    rng = random.SystemRandom(); ps = list(pieces); rng.shuffle(ps)
    body = "\n\n".join(f"【{i + 1}】\n{t.strip()[:600]}" for i, (_, t) in enumerate(ps))    # 每样料只剪开头 600 字
    frags = clean(_ask(PROMPT.format(n=n, body=body), temperature), n)
    rng.shuffle(frags)
    return frags
