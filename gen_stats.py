#!/usr/bin/env python3
"""v2 (2026-07-10): findyourmonkey.com stats — aggregates ALL channels live.
- YouTube: channel totals via API (shannan token has read scope) for every handle in CHANNELS
- Instagram: account views (trailing 30d) + media count via Graph API
- Clip wall: top shorts from cookie_MASTER/clip_stats.json (per-clip data)
Pushes to GitHub Pages only when numbers change. Timer: fym-site-stats.timer 08:10.
Run with conda python: /var/home/findyourmonkey/miniconda/envs/ai-work/bin/python3"""
import json, subprocess, os, sys, datetime
from pathlib import Path

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
    ok = False
    for h in CHANNELS:
        try:
            r = yt.channels().list(part="statistics", forHandle=h).execute()
            st = r["items"][0]["statistics"]
            views += int(st.get("viewCount", 0)); vids += int(st.get("videoCount", 0)); subs += int(st.get("subscriberCount", 0))
            ok = True
        except Exception as e:
            print(f"yt {h}: {e}", file=sys.stderr)
    # 14 Aug -- same cache-don't-zero fix as top_wall(), same root cause
    # (YouTube quota exhaustion). This is the SEPARATE function that feeds
    # the headline "X views" number specifically -- fixing top_wall() alone
    # restored the individual clip tiles but left this aggregate still
    # silently dropping to 0 every quota-exhausted run, which is why the
    # headline total was still wrong even after the tiles were showing
    # real YouTube clips again. Same fix, same reasoning: cache the last
    # real total, fall back to it on failure, never overwrite real data
    # with a zero caused by an API limit rather than an actual change.
    cache_path = Path(__file__).parent / "yt_totals_cache.json"
    if ok:
        try:
            cache_path.write_text(json.dumps({"views": views, "vids": vids, "subs": subs}))
        except Exception as e:
            print(f"yt totals cache write failed: {e}", file=sys.stderr)
        return views, vids, subs
    try:
        c = json.loads(cache_path.read_text())
        print(f"yt totals: live fetch failed (quota?), using cached {c['views']} views", file=sys.stderr)
        return c["views"], c["vids"], c["subs"]
    except Exception:
        print("yt totals: live fetch failed and no cache available", file=sys.stderr)
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

    # 14 Aug -- CACHE, DON'T ZERO. YouTube's API has been quota-exhausted
    # (403 quotaExceeded) on every single channel since ~8 Aug, so allstats
    # comes back completely empty every run, and this function used to just
    # return that empty list -- which meant every automated run since then
    # silently OVERWROTE the last real YouTube numbers with zero instead of
    # just failing to update them. Chris caught it from the outside: the
    # site's total dropped from over 2M to ~960K, and every top-clip tile
    # was suddenly Instagram-only, because the real 114K/34K/32K YouTube
    # shorts had been erased by a failed fetch, not because they stopped
    # performing. Fix: cache the last GOOD result and fall back to it
    # whenever a run comes back empty, so a quota failure means "this run
    # didn't update," never "the real numbers are gone."
    cache_path = Path(__file__).parent / "yt_wall_cache.json"
    if top:
        try:
            cache_path.write_text(json.dumps(top))
        except Exception as e:
            print(f"yt wall cache write failed: {e}", file=sys.stderr)
        return top
    try:
        cached = json.loads(cache_path.read_text())
        print(f"yt wall: live fetch empty (quota?), using cached {len(cached)} entries", file=sys.stderr)
        return cached
    except Exception:
        print("yt wall: live fetch empty and no cache available", file=sys.stderr)
        return []

def ig_wall(n=8):
    """2026-07-17: top IG reels for the clip wall. Views come from
    ig_performance_insights.json (ig-analytics.timer, daily 11am); permalink +
    thumbnail fetched per-media from the Graph API. Guaranteed n slots so IG's
    best isn't drowned out by big YT clips in a pure sort.
    9 Aug -- n raised 3 -> 8 and slots now SAMPLE from the real pool instead
    of always the exact same fixed top-N. Chris: "cycle newer clips in...
    we have some cool ones to show off." Same shape as the leaderboard
    rotation pattern: always include the single best clip so the current
    standout (a 178K-view breakout, ~40x the next entry) never disappears,
    then randomly sample the REST from everything above a real floor (500
    views -- high enough to exclude noise, low enough that a fresh clip a
    day or two old can realistically clear it) so a repeat visitor sees a
    different mix, not a frozen top-3 from whenever this was last glanced at.
    Falls back to a strict view-sorted top-n if the pool is smaller than n,
    so the wall can never come up short because the bar was set too high.
    """
    import random
    import requests
    sys.path.insert(0, "/var/home/findyourmonkey/projects/shared")
    from instagram_poster import IG_TOKEN
    out = []
    try:
        ig = json.load(open("/var/home/findyourmonkey/projects/shared/ig_performance_insights.json"))
        all_posts = ig.get("all_posts", [])
        ranked = sorted(all_posts, key=lambda p: -(p.get("views") or 0))
        pool = [p for p in ranked if (p.get("views") or 0) >= 500]
        if len(pool) >= n:
            picks = ([ranked[0]] if ranked else []) + random.sample(
                [p for p in pool if p is not (ranked[0] if ranked else None)],
                min(n - 1, len(pool) - 1))
        else:
            picks = ranked[:n]
        for p in picks:
            if len(out) >= n: break
            try:
                m = requests.get(f"https://graph.facebook.com/v21.0/{p['id']}",
                    params={"fields": "permalink,thumbnail_url,media_url", "access_token": IG_TOKEN},
                    timeout=20).json()
                url = m.get("permalink"); thumb = m.get("thumbnail_url") or m.get("media_url")
                if url and thumb:
                    out.append({"id": p["id"], "views": p.get("views", 0),
                                "platform": "ig", "url": url, "thumb": thumb,
                                "name": p.get("comedian") or ""})
            except Exception as e:
                print(f"ig_wall {p.get('id')}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"ig_wall: {e}", file=sys.stderr)
    return out

def yt_views_30d(current_yv):
    """14 Aug -- Chris: 'shouldn't [last 30 days] be combined with YouTube??'
    He was right -- 'views_30d_ig' was IG-only despite the site labeling it
    just 'LAST 30 DAYS', no YouTube in it at all. YouTube's channel stats
    endpoint only gives an all-time cumulative total, no date-windowed
    number the way IG's Insights API does -- but git history IS a real
    daily snapshot of that same all-time total, going back well past 30
    days. today's yt_views minus yt_views from ~30 days ago is a genuine,
    exact delta -- actual views gained in the window, computed from data
    already sitting in the repo, zero API calls, so it isn't even affected
    by the YouTube quota problem. Returns 0 (not a guess) if history
    doesn't reach back far enough yet, so it degrades honestly rather than
    fabricating a number."""
    try:
        commit = subprocess.run(
            ["git", "-C", str(Path(__file__).parent), "log", "--before=30 days ago",
             "--format=%H", "-1", "--", "clips.json"],
            capture_output=True, text=True, timeout=15).stdout.strip()
        if not commit:
            return 0
        old = subprocess.run(
            ["git", "-C", str(Path(__file__).parent), "show", f"{commit}:clips.json"],
            capture_output=True, text=True, timeout=15).stdout
        old_yv = json.loads(old).get("yt_views", 0)
        return max(0, current_yv - old_yv)
    except Exception as e:
        print(f"yt_views_30d: {e}", file=sys.stderr)
        return 0

def main():
    yv, yvids, ysubs = yt_totals()
    igv30, igmedia, igfol = ig_totals()
    yv30 = yt_views_30d(yv)
    payload = {
        "updated": datetime.date.today().isoformat(),
        "total_views": yv + igv30,          # YT all-time + IG trailing-30 (both real, both live)
        "total_clips": yvids + igmedia,     # everything published
        # 14 Aug -- now genuinely combined, both platforms, real 30-day
        # windows for both (YT via git-history delta, IG via its own API).
        # views_30d_ig kept alongside for anyone who wants the IG-only
        # breakdown specifically, but the headline number is the honest
        # whole-empire figure now, matching what the label actually says.
        "views_30d": yv30 + igv30,
        "views_30d_ig": igv30,
        "views_30d_yt": yv30,
        "followers": ysubs + igfol,
        "yt_views": yv,
        # 2026-07-17: wall = top 9 YT + top 3 IG (guaranteed slots), sorted by views
        "top": sorted(top_wall()[:9] + ig_wall(8), key=lambda x: -x.get("views", 0)),
    }
    old = None
    if os.path.exists(OUT):
        try: old = json.load(open(OUT))
        except Exception: pass

    # 14 Aug -- THE CEMENT. Chris: "how do we get these things in cement?
    # instead of me finding problems a month later and having to fix them
    # again and again?" Today's whole YouTube-quota mess sat live for six
    # days before anyone caught it, purely because nothing was watching FOR
    # it -- every run "succeeded" by its own definition even while quietly
    # publishing a wrong number. Same shape as every watchdog built earlier
    # tonight (network, sms, clip batches): check the thing that actually
    # matters, not just whether the script exited 0. Real views only ever
    # go UP -- any drop, or any core number going to exactly zero when it
    # wasn't before, is not a "new normal," it's a bug, every time. Runs on
    # EVERY execution, publish or not, so a problem gets caught same-day,
    # not discovered by Chris scrolling the site weeks later.
    def _flag(msg):
        print(f"[SANITY] {msg}", file=sys.stderr)
        try:
            sys.path.insert(0, "/var/home/findyourmonkey/projects/shared")
            import email_sender
            email_sender.send_email("findyourmonkey@gmail.com",
                f"⚠️ Site stats sanity check failed: {msg[:60]}",
                f"{msg}\n\nCaught automatically by gen_stats.py's own sanity check, "
                f"same run that would have published it. Nothing was published "
                f"differently because of this alert -- it's a heads-up, not a block; "
                f"go look at yt_wall_cache.json / yt_totals_cache.json / the git log "
                f"for clips.json to see what actually happened.")
        except Exception as e:
            print(f"[SANITY] alert email failed: {e}", file=sys.stderr)

    if old:
        # 15 Aug -- was "any drop at all", and it flooded Chris's inbox:
        # 4 alerts in under an hour, every one a few hundred views on a
        # 2.28M total (2283239 -> 2282998, etc). Checked the real cause --
        # YouTube's number is frozen right now (still reading the quota-
        # exhaustion cache, unchanged run to run), so the wobble is
        # Instagram's OWN Insights API returning a slightly different
        # "views, last 30 days" figure between calls a few minutes apart.
        # That's normal for a live platform estimate, not a bug -- the
        # REAL incident this check exists for (the YouTube quota disaster)
        # dropped the total by well over a MILLION views, not a few
        # hundred. A check that can't tell those apart isn't calibrated,
        # it's just noisy, and a watchdog nobody trusts because it cries
        # wolf is worse than no watchdog. Threshold: only flag a drop past
        # 0.5% of the previous total, which a few hundred views out of
        # 2.28M never clears, but a real collapse clears immediately.
        views_drop_threshold = old.get("total_views", 0) * 0.005
        views_drop = old.get("total_views", 0) - payload["total_views"]
        if views_drop > views_drop_threshold:
            _flag(f"total_views dropped: {old['total_views']:,} -> {payload['total_views']:,} (-{views_drop:,}, past the 0.5% noise floor)")
        if payload["total_clips"] < old.get("total_clips", 0):
            _flag(f"total_clips dropped: {old['total_clips']:,} -> {payload['total_clips']:,}")
        if old.get("yt_views", 0) > 0 and payload["yt_views"] == 0:
            _flag("yt_views went to exactly 0 (was nonzero) -- looks like a silent API failure, not a real drop")
        if old.get("views_30d", 0) > 0 and payload.get("views_30d", 0) < old["views_30d"] * 0.5:
            _flag(f"views_30d fell by more than half: {old['views_30d']:,} -> {payload.get('views_30d', 0):,}")

    if old and old.get("total_views") == payload["total_views"] and [c["id"] for c in old.get("top", [])] == [c["id"] for c in payload["top"]]:
        print("no change"); return
    json.dump(payload, open(OUT, "w"), indent=1)
    subprocess.run(["git", "-C", REPO, "add", "clips.json"], check=True)
    subprocess.run(["git", "-C", REPO, "commit", "-m", f"stats {payload['updated']}: {payload['total_views']:,} views"], check=True)
    subprocess.run(["git", "-C", REPO, "push", "origin", "main"], check=True)
    print(f"pushed: {payload['total_views']:,} views / {payload['total_clips']:,} published")

if __name__ == "__main__":
    main()
