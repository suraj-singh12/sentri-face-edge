#!/usr/bin/env python3
"""Collect real Marvel-actor photographs from Wikimedia Commons for local QA.

Python 3.12+, standard library only. Nothing is uploaded. No face inference.

  python scripts/fetch_marvel_photos.py --per-actor 8
  python scripts/fetch_marvel_photos.py --verify
  python scripts/fetch_marvel_photos.py --restore

The generated manifest is a candidate library: a human must verify actor labels,
faces, image quality, and reference/query splits before claiming recognition accuracy.
Preserve manifest.json and photographs together to reproduce a QA run.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
AGENT = "SentriFace-QA-photo-fixtures/1.0 (https://github.com/suraj-singh12/sentri-face-edge) python-urllib"
DEFAULT_ACTORS = (
    "Robert Downey Jr", "Chris Evans", "Scarlett Johansson", "Chris Hemsworth",
    "Mark Ruffalo", "Jeremy Renner", "Samuel L Jackson", "Tom Holland",
    "Benedict Cumberbatch", "Elizabeth Olsen", "Brie Larson", "Paul Rudd",
    "Anthony Mackie", "Sebastian Stan", "Florence Pugh", "Zoe Saldana",
    "Letitia Wright", "Tessa Thompson", "Danai Gurira", "Natalie Portman",
    "Chadwick Boseman", "Lupita Nyongo", "Karen Gillan", "Tom Hiddleston",
    "Chris Pratt", "Pom Klementieff", "Hailee Steinfeld", "Iman Vellani",
    "Simu Liu", "Tatiana Maslany", "Oscar Isaac", "Mahershala Ali",
    "Hayley Atwell", "Evangeline Lilly", "Gwyneth Paltrow", "Don Cheadle",
)
BLOCKED_TITLE = re.compile(r"poster|drawing|illustrat|painting|comic|cosplay|statue|waxwork|wax.figure|sketch|fanart|fan.art|logo|costume design|animated|video.game|screenshot|soundtrack|svg", re.I)
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def key(value: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")


def actor_match(actor: str, filename: str) -> bool:
    # Fail closed on weak labels. Commons descriptions can mention an actor without depicting them.
    words = [w for w in key(actor).split("-") if w not in {"jr", "sr", "l"}]
    title = key(filename)
    return len(words) >= 2 and all(w in title.split("-") for w in words[:2])


def license_ok(license_name: str, license_url: str) -> bool:
    name = re.sub(r"[^a-z0-9]+", "-", (license_name or "").lower()).strip("-")
    url = (license_url or "").lower()
    if any(bad in name + url for bad in ("noncommercial", "-nc", "/nc/", "fairuse", "allrightsreserved")):
        return False
    return (name.startswith(("cc-by", "cc0", "publicdomain", "public-domain", "pd-"))
            or "creativecommons.org/licenses/by/" in url
            or "creativecommons.org/licenses/by-sa/" in url
            or "creativecommons.org/publicdomain/" in url)


def request(url: str, *, max_bytes: int = 1_500_000) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("HTTPS is required")
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json,image/*;q=0.9,*/*;q=0.5"})
            with urllib.request.urlopen(req, timeout=45) as response:
                final_host = urllib.parse.urlparse(response.geturl()).hostname or ""
                if final_host not in {"commons.wikimedia.org", "upload.wikimedia.org"}:
                    raise ValueError("Unexpected download host: " + final_host)
                chunks = []
                total = 0
                while True:
                    part = response.read(128 * 1024)
                    if not part:
                        break
                    total += len(part)
                    if total > max_bytes:
                        raise ValueError("File exceeds configured download limit")
                    chunks.append(part)
                return b"".join(chunks)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            delay = exc.headers.get("Retry-After", "")
            time.sleep(min(30, int(delay)) if delay.isdigit() else (2 ** attempt + 2))
        except (TimeoutError, urllib.error.URLError):
            if attempt == 3:
                raise
            time.sleep(2 ** attempt + 1)
    raise RuntimeError("Download failed")


def api_search(actor: str, limit: int) -> list[dict]:
    # Fetch at most 50 titles; expensive extmetadata is read for only the first batch.
    qs = urllib.parse.urlencode({
        "action": "query", "format": "json", "formatversion": "2",
        "generator": "search", "gsrsearch": '"' + actor + '"',
        "gsrnamespace": "6", "gsrlimit": str(min(50, max(15, limit * 4))),
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
        "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|Credit|UsageTerms",
        "iiurlwidth": "1400", "maxlag": "5",
    })
    data = json.loads(request(API + "?" + qs))
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    return data.get("query", {}).get("pages", [])


def get_meta(info: dict, name: str) -> str:
    v = info.get("extmetadata", {}).get(name, {})
    return clean(v.get("value", "")) if isinstance(v, dict) else ""


def candidate(actor: str, page: dict) -> dict | None:
    title = page.get("title", "")
    if not title.startswith("File:") or BLOCKED_TITLE.search(title) or not actor_match(actor, title):
        return None
    info = (page.get("imageinfo") or [None])[0]
    if not info or info.get("mime") not in IMAGE_TYPES:
        return None
    if min(info.get("width", 0), info.get("height", 0)) < 450:
        return None
    license_name = get_meta(info, "LicenseShortName")
    license_url = get_meta(info, "LicenseUrl")
    if not license_ok(license_name, license_url):
        return None
    url = info.get("thumburl") or info.get("url", "")
    if urllib.parse.urlparse(url).hostname not in {"upload.wikimedia.org", "commons.wikimedia.org"}:
        return None
    photo_id = hashlib.sha256(title.encode("utf-8")).hexdigest()[:12]
    return {
        "id": photo_id, "actor": actor, "commons_file": title,
        "page": info.get("descriptionurl") or "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
        "url": url, "author": get_meta(info, "Artist"),
        "credit": get_meta(info, "Credit"), "license": license_name,
        "license_url": license_url, "file": key(actor) + "/" + photo_id + IMAGE_TYPES[info["mime"]],
        "sha256": "", "bytes": 0, "reviewed": False,
        "review_notes": "Confirm this is the named real actor and annotate pose/lighting/visible faces before biometric claims.",
    }


def atomic_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf8", dir=path.parent, delete=False) as temp:
        json.dump(obj, temp, ensure_ascii=False, indent=2)
        temp.write("\n")
        temp_name = temp.name
    os.replace(temp_name, path)


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "source": "Wikimedia Commons", "photos": []}
    data = json.loads(path.read_text(encoding="utf8"))
    if data.get("version") != 1 or not isinstance(data.get("photos"), list):
        raise ValueError("Unsupported manifest version")
    return data


def image_valid(blob: bytes, extension: str) -> bool:
    if len(blob) < 5000:
        return False
    return blob.startswith(b"\xff\xd8\xff") if extension == ".jpg" else blob.startswith(b"\x89PNG\r\n\x1a\n")


def download(row: dict, root: Path, max_mb: int) -> str:
    rel = Path(row["file"])
    if rel.is_absolute() or ".." in rel.parts or len(rel.parts) != 2 or rel.suffix not in (".jpg", ".png"):
        raise ValueError("Unsafe manifest path")
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if row.get("sha256") and row["sha256"] != digest:
            raise ValueError("Existing photo hash differs from pinned manifest; will not overwrite")
        if not image_valid(content, path.suffix):
            raise ValueError("Existing image is invalid")
    else:
        content = request(row["url"], max_bytes=max_mb * 1_000_000)
        if not image_valid(content, path.suffix):
            raise ValueError("Invalid or empty image")
        digest = hashlib.sha256(content).hexdigest()
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
            temp.write(content)
            tempname = temp.name
        os.replace(tempname, path)
    row["sha256"] = digest
    row["bytes"] = len(content)
    return digest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=Path("qa-fixtures/marvel-actors"), help="Local ignored directory")
    p.add_argument("--actors-file", type=Path, help="One actor's real name per line; default is 36 Marvel actors")
    p.add_argument("--per-actor", type=int, default=8, help="Desired candidate images per actor")
    p.add_argument("--max-mb", type=int, default=15, help="Maximum bytes per photo in MB")
    action = p.add_mutually_exclusive_group()
    action.add_argument("--verify", action="store_true", help="Offline verify downloaded photos and pinned hashes")
    action.add_argument("--restore", action="store_true", help="Re-download exactly the URLs saved in manifest.json")
    args = p.parse_args(argv)
    if not 1 <= args.per_actor <= 50 or not 1 <= args.max_mb <= 50:
        p.error("per-actor must be 1..50; max-mb must be 1..50")
    root = args.out.expanduser().resolve()
    manifest = root / "manifest.json"
    data = load_manifest(manifest)
    records = {x["id"]: x for x in data["photos"]}
    actors = list(DEFAULT_ACTORS)
    if args.actors_file:
        actors = [line.strip() for line in args.actors_file.read_text(encoding="utf8").splitlines()
                  if line.strip() and not line.strip().startswith("#")]
    problems = []
    if (args.verify or args.restore) and not records:
        print("No saved photos to verify or restore; run discovery first.", file=sys.stderr)
        return 1
    if not (args.verify or args.restore):
        for actor in dict.fromkeys(actors):
            print("SEARCH", actor, flush=True)
            try:
                choices = [c for page in api_search(actor, args.per_actor)
                           if (c := candidate(actor, page)) is not None]
                # Older reviewed records are never reset by discovery.
                for row in choices[:args.per_actor]:
                    records.setdefault(row["id"], row)
                print("  candidates:", len(choices[:args.per_actor]))
            except Exception as exc:
                problems.append(actor + ": " + str(exc))
            time.sleep(0.3)
    for row in records.values():
        if args.verify:
            try:
                path = root / row["file"]
                content = path.read_bytes()
                assert row.get("sha256") and hashlib.sha256(content).hexdigest() == row["sha256"]
                assert image_valid(content, path.suffix)
            except (OSError, AssertionError) as exc:
                problems.append(row["file"] + ": missing, invalid or hash mismatch")
            continue
        if row.get("sha256") and (root / row["file"]).exists() and not args.restore:
            continue
        try:
            download(row, root, args.max_mb)
            print("OK", row["file"])
        except (OSError, ValueError, urllib.error.URLError, RuntimeError) as exc:
            problems.append(row["file"] + ": " + str(exc))
            print("FAILED", row["file"], str(exc), file=sys.stderr)
        time.sleep(0.3)
    data["photos"] = sorted(records.values(), key=lambda x: (x["actor"], x["id"]))
    if not args.verify:
        atomic_json(manifest, data)
    valid = sum(bool(r.get("sha256")) and (root / r["file"]).exists() for r in data["photos"])
    if not data["photos"]:
        problems.append("No candidates found; check Commons access, search terms and licenses")
    reviewed = sum(bool(r.get("reviewed")) for r in data["photos"])
    print(f"Photos: {valid}/{len(data['photos'])}; human-reviewed: {reviewed}; errors: {len(problems)}; manifest: {manifest}")
    for err in problems:
        print(" -", err, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())