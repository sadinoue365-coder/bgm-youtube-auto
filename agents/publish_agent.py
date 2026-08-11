"""
予約公開（publishAt）ヘルパー

アップロード完了時刻がジョブの所要時間でブレても、
YouTube側で毎回決まった時刻に公開されるようにする。

仕組み: 動画を「非公開 + publishAt(公開予定時刻)」でアップロードすると、
YouTubeが指定時刻ちょうどに自動で公開する。
"""

from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


def next_publish_time_utc(hour_jst: int, minute: int = 0, buffer_minutes: int = 15) -> datetime:
    """
    次の「JSTでの定時スロット」をUTC datetimeで返す。

    例: hour_jst=18 で現在17:00 JSTなら今日18:00 JST、
        現在18:10 JSTなら明日18:00 JST。
    buffer_minutes: 公開時刻まで最低これだけ余裕を持たせる
    （YouTubeの処理時間・サムネ反映を考慮）。
    """
    now_jst = datetime.now(JST)
    candidate = now_jst.replace(hour=hour_jst, minute=minute, second=0, microsecond=0)
    if candidate <= now_jst + timedelta(minutes=buffer_minutes):
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def to_rfc3339(dt_utc: datetime) -> str:
    """YouTube APIのpublishAtに渡すRFC3339文字列に変換する。"""
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.0Z")
