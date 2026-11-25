"""算两句话意思像不像。我们家用本机 ollama 里的 bge-m3，梦的句子和她说的话都不出这台机器。

换成别的模型或别家的接口，只改 embed() 里面就行，回一组向量。
注意：换了模型，「多像才算像」的那几个门槛不能照抄我们的数，要拿自己的句子重新量。
"""
import json, math, os, urllib.request

OLLAMA = os.environ.get("DREAM_OLLAMA", "http://127.0.0.1:11434")
MODEL = os.environ.get("DREAM_EMBED_MODEL", "bge-m3")


def embed(texts):
    """texts: 一组字符串 -> 一组向量"""
    req = urllib.request.Request(f"{OLLAMA}/api/embed", data=json.dumps({"model": MODEL, "input": texts}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r: return json.load(r)["embeddings"]


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) + 1e-9)
