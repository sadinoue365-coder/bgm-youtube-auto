import ssl
import time

from googleapiclient.errors import HttpError

_MAX_RETRIES = 5


def add_to_playlist(youtube_service, video_id, playlist_id):
    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id,
            },
        }
    }
    retry = 0
    while True:
        try:
            youtube_service.playlistItems().insert(
                part="snippet", body=body
            ).execute()
            print(f"  Added to playlist: {playlist_id}")
            return
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504):
                retry += 1
                if retry > _MAX_RETRIES:
                    raise
                wait = min(2 ** retry, 64)
                print(f"  HTTP {e.resp.status} エラー、{wait}秒後にリトライ ({retry}/{_MAX_RETRIES})...")
                time.sleep(wait)
            else:
                raise
        except (ssl.SSLEOFError, ssl.SSLError, ConnectionResetError, BrokenPipeError, OSError) as e:
            retry += 1
            if retry > _MAX_RETRIES:
                raise
            wait = min(2 ** retry, 64)
            print(f"  ネットワークエラー ({type(e).__name__})、{wait}秒後にリトライ ({retry}/{_MAX_RETRIES})...")
            time.sleep(wait)
