#!/usr/bin/env python3
"""v2 (2026-07-10): findyourmonkey.com stats — aggregates ALL channels live.
- YouTube: channel totals via API (shannan token has read scope) for every handle in CHANNELS
- Instagram: account views (trailing 30d) + media count via Graph API
- Clip wall: top shorts from cookie_MASTER/clip_stats.json (per-clip data)
Pushes to GitHub Pages only when numbers change. Timer: fym-site-stats.timer 08:10.
Run with conda python: /var/home/findyourmonkey/miniconda/envs/ai-work/bin/python3"""
import json, subprocess, os, sys, datetime

REPO = "/var/home/findyourmonkey/projects/findyourmonkey-site"
OUT = os.path.join(REPO, "clips.json")
CLIP_SRC = "/var/home/findyourmonkey/projects/cookie_MASTER/clip_stats.json"
YT_TOKEN = "/var/home/findyourmonkey/projects/shannan_pipeline/youtube_credentials.json"
CHANNELS = ["findyourmonkey", "RyanVersion0", "OpenMicClips", "TCVlogs96"]  # add handles here
IG_ID = "17841469779642555"
EXCLUDE = {"JOGEUHGGHDE","e66WhxjPqY8","D24gQX63JPk","3GZX9DgRwjk"}

def yt_totals():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_info(json.load(open(YT_TOKEN)))
    yt = build("youtube", "v3", credentials=creds)
    views = vids = subs = 0
    for h in CHANNELS:
        try:
            r = yt.channels().list(part="statistics", forHandle=h).execute()
            st = r["items"][0]["statistics"]
            views += int(st.get("viewCount", 0)); vids += int(st.get("videoCount", 0)); subs += int(st.get("subscriberCount", 0))
        except Exception as e:
            print(f"yt {h}: {e}", file=sys.stderr)
    return views, vids, subs

def ig_totals():
    import requests
    sys.path.insert(0, "/var/home/findyourmonkey/projects/shared")
    from instagram_poster import IG_TOKEN
    views30 = media = followers = 0
    try:
        a = requests.get(f"https://graph.facebook.com/v21.0/{IG_ID}",
            params={"fields": "followers_count,media_count", "access_token": IG_TOKEN}, timeout=20).json()
        media = a.get("media_count", 0); followers = a.get("followers_count", 0)
        i = requests.get(f"https://graph.facebook.com/v21.0/{IG_ID}/insights",
            params={"metric": "views", "period": "day", "metric_type": "total_value",
                    "since": "-30 days", "access_token": IG_TOKEN}, timeout=20).json()
        views30 = i["data"][0]["total_value"]["value"]
    except Exception as e:
        print(f"ig: {e}", file=sys.stderr)
    return views30, media, followers

def top_wall():
    """v2.1: all-time top shorts via API (clip_stats only tracked last-7d uploads,
    so all-time hits like the 113K short never made the wall)."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_info(json.load(open(YT_TOKEN)))
    yt = build("youtube", "v3", credentials=creds)
    allstats = []
    for h in CHANNELS:
        try:
            ch = yt.channels().list(part="contentDetails", forHandle=h).execute()
            up = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            ids, page = [], None
            while True:
                r = yt.playlistItems().list(part="contentDetails", playlistId=up,
                                            maxResults=50, pageToken=page).execute()
                ids += [i["contentDetails"]["videoId"] for i in r["items"]]
                page = r.get("nextPageToken")
                if not page: break
            for i in range(0, len(ids), 50):
                vr = yt.videos().list(part="statistics,contentDetails", id=",".join(ids[i:i+50])).execute()
                for v in vr["items"]:
                    dur = v["contentDetails"].get("duration", "")
                    if "H" in dur: continue  # shorts wall only — skip long-form
                    allstats.append({"id": v["id"], "views": int(v["statistics"].get("viewCount", 0))})
        except Exception as e:
            print(f"wall {h}: {e}", file=sys.stderr)
    top = [x for x in sorted(allstats, key=lambda x: -x["views"]) if x["id"] not in EXCLUDE][:12]
    return top

def ig_wall(n=3):
    """2026-07-17: top IG reels for the clip wall. Views come from
    ig_performance_insights.json (ig-analytics.timer, daily 11am); permalink +
    thumbnail fetched per-media from the Graph API. Guaranteed n slots so IG's
    best (5.7K) isn't drowned out by 114K YT clips in a pure sort."""
    import requests
    sys.path.insert(0, "/var/home/findyourmonkey/projects/shared")
    from instagram_poster import IG_TOKEN
    out = []
    try:
        ig = json.load(open("/var/home/findyourmonkey/projects/shared/ig_performance_insights.json"))
        posts = sorted(ig.get("all_posts", []), key=lambda p: -(p.get("views") or 0))
        for p in posts:
            if len(out) >= n: break
            try:
                m = requests.get(f"https://graph.facebook.com/v21.0/{p['id']}",
                    params={"fields": "permalink,thumbnail_url,media_url", "access_token": IG_TOKEN},
                    timeout=20).json()
                url = m.get("permalink"); thumb = m.get("thumbnail_url") or m.get("media_url")
                if url and thumb:
                    out.append({"id": p["id"], "views": p.get("views", 0),
                                "platform": "ig", "url": url, "thumb": thumb})
            except Exception as e:
                print(f"ig_wall {p.get('id')}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"ig_wall: {e}", file=sys.stderr)
    return out

def main():
    yv, yvids, ysubs = yt_totals()
    igv30, igmedia, igfol = ig_totals()
    payload = {
        "updated": datetime.date.today().isoformat(),
        "total_views": yv + igv30,          # YT all-time + IG trailing-30 (both real, both live)
        "total_clips": yvids + igmedia,     # everything published
        "views_30d_ig": igv30,
        "followers": ysubs + igfol,
        "yt_views": yv,
        # 2026-07-17: wall = top 9 YT + top 3 IG (guaranteed slots), sorted by views
        "top": sorted(top_wall()[:9] + ig_wall(3), key=lambda x: -x.get("views", 0)),
    }
    old = None
    if os.path.exists(OUT):
        try: old = json.load(open(OUT))
        except Exception: pass
    if old and old.get("total_views") == payload["total_views"] and [c["id"] for c in old.get("top", [])] == [c["id"] for c in payload["top"]]:
        print("no change"); return
    json.dump(payload, open(OUT, "w"), indent=1)
    subprocess.run(["git", "-C", REPO, "add", "clips.json"], check=True)
    subprocess.run(["git", "-C", REPO, "commit", "-m", f"stats {payload['updated']}: {payload['total_views']:,} views"], check=True)
    subprocess.run(["git", "-C", REPO, "push", "origin", "main"], check=True)
    print(f"pushed: {payload['total_views']:,} views / {payload['total_clips']:,} published")

if __name__ == "__main__":
    main()
