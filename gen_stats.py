#!/usr/bin/env python3
"""Regenerate clips.json for findyourmonkey.com from cookie_MASTER/clip_stats.json.
Run by fym-site-stats.timer daily. Pushes to GitHub Pages only if data changed."""
import json, subprocess, os
SRC = "/var/home/findyourmonkey/projects/cookie_MASTER/clip_stats.json"
REPO = "/var/home/findyourmonkey/projects/findyourmonkey-site"
OUT = os.path.join(REPO, "clips.json")
# IDs excluded from the public wall (edgy titles/thumbs, not studio-front material)
EXCLUDE = {"JOGEUHGGHDE","e66WhxjPqY8","D24gQX63JPk","3GZX9DgRwjk"}

d = json.load(open(SRC))
best = {}
for c in d:
    v = c.get("views", 0) or 0
    if c["video_id"] not in best or v > best[c["video_id"]]["views"]:
        c = dict(c); c["views"] = v; best[c["video_id"]] = c

total_views = sum(x["views"] for x in best.values())
total_likes = sum(x.get("likes", 0) or 0 for x in best.values())
top = [x for x in sorted(best.values(), key=lambda x: x["views"], reverse=True)
       if x["video_id"] not in EXCLUDE][:12]

payload = {
    "updated": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d"),
    "total_views": total_views,
    "total_likes": total_likes,
    "total_clips": len(best),
    "top": [{"id": t["video_id"], "views": t["views"]} for t in top],
}
old = None
if os.path.exists(OUT):
    try: old = json.load(open(OUT))
    except Exception: pass
if old and old.get("total_views") == payload["total_views"] and [c["id"] for c in old.get("top", [])] == [c["id"] for c in payload["top"]]:
    print("no change"); raise SystemExit(0)
json.dump(payload, open(OUT, "w"), indent=1)
subprocess.run(["git", "-C", REPO, "add", "clips.json"], check=True)
subprocess.run(["git", "-C", REPO, "commit", "-m", f"stats refresh {payload['updated']}: {total_views:,} views"], check=True)
subprocess.run(["git", "-C", REPO, "push", "origin", "main"], check=True)
print(f"pushed: {total_views:,} views, {len(best)} clips")
