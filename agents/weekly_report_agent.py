"""
週次パフォーマンスレポート — 全4チャンネル (HTML メール版)

毎週月曜日に直近7日間の各チャンネル成績をまとめ、HTMLメールを生成する。
"""

import json
import os
import statistics
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from agents.optimization_log import get_lift_stats


CHANNEL_CONFIGS = {
    "Jazz": {
        "client_secret_env": "JAZZ_CLIENT_SECRET_JSON",
        "refresh_token_env": "JAZZ_REFRESH_TOKEN",
        "emoji": "🎷",
        "color": "#C0392B",
    },
    "Sleep": {
        "client_secret_env": "SLEEP_CLIENT_SECRET_JSON",
        "refresh_token_env": "SLEEP_REFRESH_TOKEN",
        "emoji": "🌙",
        "color": "#2C3E50",
    },
    "Cafe": {
        "client_secret_env": "CAFE_CLIENT_SECRET_JSON",
        "refresh_token_env": "CAFE_REFRESH_TOKEN",
        "emoji": "☕",
        "color": "#8B6914",
    },
}


def get_credentials(client_secret_json, refresh_token):
    client_info = json.loads(client_secret_json)
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_info["installed"]["client_id"],
        client_secret=client_info["installed"]["client_secret"],
        scopes=["https://www.googleapis.com/auth/youtube"],
    )
    creds.refresh(Request())
    return creds


def get_channel_stats(youtube, days=14):
    ch = youtube.channels().list(part="contentDetails,snippet,statistics", mine=True).execute()
    ch_item = ch["items"][0]
    playlist_id = ch_item["contentDetails"]["relatedPlaylists"]["uploads"]
    ch_name = ch_item["snippet"]["title"]
    total_subs = int(ch_item["statistics"].get("subscriberCount", 0))

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    videos = []
    page_token = None
    while True:
        kwargs = dict(part="snippet", playlistId=playlist_id, maxResults=50)
        if page_token:
            kwargs["pageToken"] = page_token
        resp = youtube.playlistItems().list(**kwargs).execute()
        for item in resp.get("items", []):
            pub_str = item["snippet"]["publishedAt"]
            pub_dt = datetime.strptime(pub_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if pub_dt >= since:
                videos.append({
                    "id": item["snippet"]["resourceId"]["videoId"],
                    "title": item["snippet"]["title"],
                    "published_at": pub_dt,
                })
            else:
                page_token = None
                break
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    if not videos:
        return ch_name, total_subs, [], []

    ids = ",".join(v["id"] for v in videos)
    stats_resp = youtube.videos().list(part="statistics", id=ids).execute()
    stats_map = {s["id"]: s["statistics"] for s in stats_resp.get("items", [])}

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    this_week, last_week = [], []

    for v in videos:
        s = stats_map.get(v["id"], {})
        views = int(s.get("viewCount", 0))
        entry = {
            "title": v["title"],
            "views": views,
            "age_days": (now - v["published_at"]).days,
            "published_at": v["published_at"],
        }
        (this_week if v["published_at"] >= week_ago else last_week).append(entry)

    return ch_name, total_subs, this_week, last_week


def trend_badge(ratio):
    if ratio >= 120:
        return '<span style="color:#27AE60;font-weight:bold">▲ {:.0f}%</span>'.format(ratio)
    elif ratio >= 100:
        return '<span style="color:#27AE60">▲ {:.0f}%</span>'.format(ratio)
    elif ratio >= 80:
        return '<span style="color:#E67E22">▼ {:.0f}%</span>'.format(ratio)
    else:
        return '<span style="color:#E74C3C;font-weight:bold">▼ {:.0f}%</span>'.format(ratio)


def build_channel_card(name, cfg, ch_name, subs, this_week, last_week):
    color = cfg["color"]
    emoji = cfg["emoji"]
    this_views = sum(v["views"] for v in this_week)
    last_views = sum(v["views"] for v in last_week)

    ratio_html = ""
    if last_views > 0:
        ratio = this_views / last_views * 100
        ratio_html = f"&nbsp;{trend_badge(ratio)}&nbsp;<small style='color:#888'>先週 {last_views:,}</small>"

    top_html = ""
    if this_week:
        top = sorted(this_week, key=lambda x: x["views"], reverse=True)[0]
        top_html = f"""
        <tr>
          <td style="padding:4px 8px;color:#888;font-size:13px;">トップ動画</td>
          <td style="padding:4px 8px;font-size:13px;">{top['title'][:45]}… <span style="color:#888">({top['views']:,} views)</span></td>
        </tr>"""

    warn_html = ""
    all_views = [v["views"] for v in this_week + last_week]
    if len(all_views) >= 3:
        median = statistics.median(all_views)
        low = [v for v in this_week if v["views"] < median * 0.5 and v["age_days"] >= 7]
        if low:
            warn_html = f"""
        <tr>
          <td colspan="2" style="padding:6px 8px;">
            <span style="background:#FFF3CD;color:#856404;padding:2px 8px;border-radius:4px;font-size:12px;">
              ⚠️ 低パフォーマンス {len(low)}本 — optimize_agent が自動改善予定
            </span>
          </td>
        </tr>"""

    return f"""
    <div style="margin-bottom:16px;border-radius:8px;overflow:hidden;border:1px solid #E0E0E0;">
      <div style="background:{color};padding:10px 16px;">
        <span style="color:white;font-size:16px;font-weight:bold;">{emoji} {name}</span>
        <span style="color:rgba(255,255,255,0.8);font-size:13px;margin-left:8px;">{ch_name}</span>
      </div>
      <table style="width:100%;background:white;border-collapse:collapse;">
        <tr>
          <td style="padding:8px 8px 4px;color:#888;font-size:13px;width:35%;">今週の視聴数</td>
          <td style="padding:8px 8px 4px;font-size:15px;font-weight:bold;">{this_views:,} views {ratio_html}</td>
        </tr>
        <tr>
          <td style="padding:4px 8px;color:#888;font-size:13px;">投稿本数</td>
          <td style="padding:4px 8px;font-size:13px;">{len(this_week)}本</td>
        </tr>
        <tr>
          <td style="padding:4px 8px;color:#888;font-size:13px;">登録者数</td>
          <td style="padding:4px 8px;font-size:13px;">{subs:,}</td>
        </tr>
        {top_html}
        {warn_html}
      </table>
    </div>"""


def run():
    now = datetime.now(timezone.utc)
    start_str = (now - timedelta(days=7)).strftime("%m/%d")
    end_str = now.strftime("%m/%d")
    subject = f"【週次レポート】BGM YouTube 4チャンネル ({start_str}〜{end_str})"

    channel_cards = []
    total_this_views = 0
    total_last_views = 0
    total_subs_all = 0

    for name, cfg in CHANNEL_CONFIGS.items():
        client_secret = os.environ.get(cfg["client_secret_env"])
        refresh_token = os.environ.get(cfg["refresh_token_env"])
        if not client_secret or not refresh_token:
            channel_cards.append(f'<p style="color:#888">{cfg["emoji"]} {name}: 認証情報なし</p>')
            continue
        try:
            creds = get_credentials(client_secret, refresh_token)
            youtube = build("youtube", "v3", credentials=creds)
            ch_name, subs, this_week, last_week = get_channel_stats(youtube)
            total_this_views += sum(v["views"] for v in this_week)
            total_last_views += sum(v["views"] for v in last_week)
            total_subs_all += subs
            channel_cards.append(build_channel_card(name, cfg, ch_name, subs, this_week, last_week))
        except Exception as e:
            channel_cards.append(f'<p style="color:#E74C3C">{cfg["emoji"]} {name}: エラー — {e}</p>')

    overall_ratio_html = ""
    if total_last_views > 0:
        ratio = total_this_views / total_last_views * 100
        overall_ratio_html = f"&nbsp;{trend_badge(ratio)}"

    # optimize_agent 効果測定サマリー
    lift_stats = get_lift_stats()
    if lift_stats.get("avg_lift"):
        avg_lift_pct = (lift_stats["avg_lift"] - 1) * 100
        sig_label = "✅ 統計的有意 (p<0.05)" if lift_stats.get("significant") else f"⚠️ 有意差なし (p={lift_stats.get('p_value', 1):.2f})"
        lift_block = f"""
    <div style="background:#F0F0F0;padding:8px 24px;">
      <span style="font-size:12px;color:#888;font-weight:bold;letter-spacing:1px;">optimize_agent 効果測定</span>
    </div>
    <div style="background:white;padding:12px 24px;border-left:1px solid #E0E0E0;border-right:1px solid #E0E0E0;">
      <table style="width:100%;border-collapse:collapse;">
        <tr>
          <td style="font-size:13px;color:#888;padding:3px 8px;">計測済み施策数</td>
          <td style="font-size:13px;padding:3px 8px;">{lift_stats['n_measured']}件</td>
        </tr>
        <tr>
          <td style="font-size:13px;color:#888;padding:3px 8px;">平均リフト率</td>
          <td style="font-size:13px;padding:3px 8px;font-weight:bold;color:{'#27AE60' if avg_lift_pct >= 0 else '#E74C3C'};">
            {'▲' if avg_lift_pct >= 0 else '▼'} {abs(avg_lift_pct):.1f}%
          </td>
        </tr>
        <tr>
          <td style="font-size:13px;color:#888;padding:3px 8px;">統計的信頼性</td>
          <td style="font-size:13px;padding:3px 8px;">{sig_label}</td>
        </tr>
      </table>
    </div>"""
    else:
        note = lift_stats.get("note", "計測データ蓄積中")
        lift_block = f"""
    <div style="background:#F0F0F0;padding:8px 24px;">
      <span style="font-size:12px;color:#888;font-weight:bold;letter-spacing:1px;">optimize_agent 効果測定</span>
    </div>
    <div style="background:white;padding:12px 24px;border-left:1px solid #E0E0E0;border-right:1px solid #E0E0E0;">
      <p style="margin:0;font-size:13px;color:#888;">📊 {note}</p>
    </div>"""

    # インサイト生成
    insights = []
    all_this_week = []
    for name, cfg in CHANNEL_CONFIGS.items():
        client_secret = os.environ.get(cfg["client_secret_env"])
        refresh_token = os.environ.get(cfg["refresh_token_env"])
        if not client_secret or not refresh_token:
            continue
        try:
            creds = get_credentials(client_secret, refresh_token)
            youtube = build("youtube", "v3", credentials=creds)
            _, _, this_week, _ = get_channel_stats(youtube, days=14)
            for v in this_week:
                v["channel"] = name
                all_this_week.append(v)
        except Exception:
            pass

    if all_this_week:
        top3 = sorted(all_this_week, key=lambda x: x["views"], reverse=True)[:3]
        insights_html = "".join([
            f'<li style="margin:4px 0;font-size:13px;">'
            f'<b>{v["channel"]}</b>: {v["title"][:40]}… '
            f'<span style="color:#27AE60">{v["views"]:,} views</span></li>'
            for v in top3
        ])
        insight_block = f"""
    <div style="background:#F0F0F0;padding:8px 24px;">
      <span style="font-size:12px;color:#888;font-weight:bold;letter-spacing:1px;">今週のトップ動画</span>
    </div>
    <div style="background:white;padding:12px 24px;border-left:1px solid #E0E0E0;border-right:1px solid #E0E0E0;">
      <ul style="margin:0;padding-left:16px;">{insights_html}</ul>
    </div>"""
    else:
        insight_block = ""

    html_body = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#F5F5F5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:600px;margin:24px auto;">

    <!-- ヘッダー -->
    <div style="background:#1A1A2E;border-radius:8px 8px 0 0;padding:20px 24px;">
      <div style="color:white;font-size:20px;font-weight:bold;">📊 BGM YouTube 週次レポート</div>
      <div style="color:rgba(255,255,255,0.6);font-size:13px;margin-top:4px;">集計期間: {start_str} 〜 {end_str}</div>
    </div>

    <!-- 全体サマリー -->
    <div style="background:white;padding:20px 24px;border-left:1px solid #E0E0E0;border-right:1px solid #E0E0E0;">
      <div style="font-size:13px;color:#888;margin-bottom:4px;">全チャンネル合計</div>
      <div style="font-size:28px;font-weight:bold;color:#1A1A2E;">
        {total_this_views:,} <span style="font-size:16px;font-weight:normal;color:#888;">views</span>
        {overall_ratio_html}
      </div>
      <div style="font-size:13px;color:#888;margin-top:4px;">総登録者数: {total_subs_all:,}</div>
    </div>

    {lift_block}

    {insight_block}

    <!-- チャンネル別内訳 -->
    <div style="background:#F0F0F0;padding:8px 24px;">
      <span style="font-size:12px;color:#888;font-weight:bold;letter-spacing:1px;">チャンネル別内訳</span>
    </div>
    <div style="background:#F5F5F5;padding:12px 16px;">
      {"".join(channel_cards)}
    </div>

    <!-- フッター -->
    <div style="background:#1A1A2E;border-radius:0 0 8px 8px;padding:14px 24px;">
      <div style="color:rgba(255,255,255,0.5);font-size:11px;">
        Generated by BGM YouTube Auto System &nbsp;|&nbsp; 毎週月曜 9:00 JST 自動送信
      </div>
    </div>

  </div>
</body>
</html>"""

    print(f"SUBJECT: {subject}")
    print(html_body[:500])

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"subject={subject}\n")
            f.write(f"html_body<<EOF\n{html_body}\nEOF\n")

    return subject, html_body


if __name__ == "__main__":
    run()
