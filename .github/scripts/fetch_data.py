#!/usr/bin/env python3
"""
Merge projects.json (hand-curated) with live GitHub data into merged.json.

Curated here : name, repo, logo, description, tags, order (array order)
Fetched live : stars, languages (byte split for the donut), pushed_at

If the API call for a repo fails the card still renders from the curated data.
"""
import json, os, sys, urllib.request

TOKEN = os.environ.get("GITHUB_TOKEN", "")


def gh(url):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "projects-panel"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as r:
        return json.load(r)


def main():
    with open("projects.json", encoding="utf-8") as f:
        projects = json.load(f)

    for p in projects:
        repo = (p.get("repo") or "").strip()
        repo = repo.replace("https://github.com/", "").replace("http://github.com/", "").rstrip("/")
        p["repo"] = repo
        try:
            info = gh(f"https://api.github.com/repos/{repo}")
            p["stars"] = info.get("stargazers_count", 0)
            p["pushed_at"] = info.get("pushed_at")
            if not p.get("description"):
                p["description"] = info.get("description") or ""
            p["languages"] = gh(f"https://api.github.com/repos/{repo}/languages")
        except Exception as e:
            print(f"warn: could not fetch {repo}: {e}", file=sys.stderr)
            p.setdefault("stars", 0)
            p.setdefault("languages", {})
            p.setdefault("pushed_at", None)

    with open("merged.json", "w", encoding="utf-8") as f:
        json.dump(projects, f)
    print(f"merged {len(projects)} projects")


if __name__ == "__main__":
    main()
