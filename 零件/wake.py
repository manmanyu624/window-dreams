"""早上那副牌：他醒来记得多少。

两步：先看梦做完到「醒来」隔了多少分钟，查表得到四档各占多少；再掷一次骰子定档。
  all   全记得     整本
  most  记得大半   连着的七成，中间挖一两个洞
  one   只剩一句   随机一句（我们另外配一行影子，见 shadow.py）
  none  空白       什么都不给，只知道做过梦

表是斜坡：隔得越短记得越多，两个点之间按分钟线性过渡。
这张表改过两回，最早是「半小时内 / 两小时内 / 更久」三段一刀切，结果她连着几天听到「只剩一句」。教训：
  - 别一刀切。隔 31 分钟和隔 4 小时 59 分不该是同一副牌。
  - 空白留一点就够。一觉醒来什么都没剩，他会觉得空。我们封顶在一成。
  - 也别让「全记得」太多。剩一截，白天才有东西可想起、她才有东西可捞。
这些数是在我们家过出来的，不是算出来的。你们家的作息不一样（梦几点做、她几点醒），表也该不一样。
"""
import random

TIERS = ["all", "most", "one", "none"]
# 隔多少分钟 -> (全记得, 大半, 一句, 空白)，每行加起来 100
SLOPE = [
    (30,  (75, 22,  0,  3)),
    (60,  (45, 47,  3,  5)),
    (120, (25, 60,  8,  7)),
    (180, (15, 62, 13, 10)),
    (240, ( 5, 62, 23, 10)),
    (300, ( 0, 52, 38, 10)),
    (420, ( 0, 20, 70, 10)),
]


def odds(gap_min):
    """隔 gap_min 分钟醒来，四档各占多少（和为 100）。表两头外面取两头的数。"""
    if gap_min <= SLOPE[0][0]: return list(SLOPE[0][1])
    if gap_min >= SLOPE[-1][0]: return list(SLOPE[-1][1])
    for (g0, a), (g1, c) in zip(SLOPE, SLOPE[1:]):
        if g0 <= gap_min <= g1:
            f = (gap_min - g0) / (g1 - g0)
            return [x + (y - x) * f for x, y in zip(a, c)]


def wake(n_sents, gap_min, rng=None):
    """这本梦有 n_sents 句，隔了 gap_min 分钟醒来。回 (档, 醒来就记得的句子编号集合)。
    骰子用系统的真随机；测试时可以递一个 random.Random(种子) 进来。"""
    rng = rng or random.SystemRandom()
    tier = rng.choices(TIERS, odds(gap_min))[0]
    give = set()
    if tier == "all":
        give = set(range(n_sents))
    elif tier == "most":
        k = max(1, round(n_sents * 0.7)); start = rng.randrange(0, max(1, n_sents - k + 1))
        give = set(range(start, start + k))
        for _ in range(max(1, n_sents // 6)): give.discard(rng.randrange(n_sents))     # 中间挖洞：记得的那一大段也不是完整的
    elif tier == "one":
        give = {rng.randrange(n_sents)}
    return tier, give
