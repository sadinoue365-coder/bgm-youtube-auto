"""
動画の長さをランダムに決定するエージェント

【EXP-01】1〜3h を高確率で選ぶ重み付きサンプリング
- 視聴完了率を高め、YouTube の推薦アルゴリズムに乗りやすくする仮説
- 評価: 4週間後に週次レポートの視聴数トレンドで判断
"""
import random

# 30分刻みで0.5h〜10h
DURATIONS = [round(x * 0.5, 1) for x in range(1, 21)]

# 重み: 1h/2h/3h を重点的に選ぶ（合計1.0になるよう正規化不要・random.choicesが自動正規化）
_WEIGHTS = {
    0.5: 1,
    1.0: 6,   # ★ 高
    1.5: 4,
    2.0: 6,   # ★ 高
    2.5: 3,
    3.0: 6,   # ★ 高
    3.5: 2,
    4.0: 2,
    4.5: 1,
    5.0: 2,
    5.5: 1,
    6.0: 2,
    6.5: 1,
    7.0: 1,
    7.5: 1,
    8.0: 1,
    8.5: 1,
    9.0: 1,
    9.5: 1,
    10.0: 1,
}
_WEIGHTS_LIST = [_WEIGHTS[d] for d in DURATIONS]


def get_random_duration():
    """重み付きランダムで長さ（時間）を返す。1h/2h/3h が高確率で選ばれる"""
    return random.choices(DURATIONS, weights=_WEIGHTS_LIST, k=1)[0]


def format_duration(hours):
    """
    タイトル用の表示文字列に変換
    0.5  → "30 Min"
    1.0  → "1 Hour"
    1.5  → "90 Min"
    2.0  → "2 Hours"
    2.5  → "2.5 Hours"
    """
    if hours == 0.5:
        return "30 Min"
    elif hours == 1.0:
        return "1 Hour"
    elif hours == 1.5:
        return "90 Min"
    elif hours % 1 == 0:
        return f"{int(hours)} Hours"
    else:
        return f"{hours} Hours"
