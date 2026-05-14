"""
動画の長さをランダムに決定するエージェント
0.5h〜10hを30分刻みでランダム選択
"""
import random

# 30分刻みで0.5h〜10h
DURATIONS = [round(x * 0.5, 1) for x in range(1, 21)]
# = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0,
#    5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0]


def get_random_duration():
    """ランダムな長さ（時間）を返す"""
    return random.choice(DURATIONS)


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
