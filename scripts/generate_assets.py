"""Generate the local SVG cards used by the profile README.

Uses PROFILE_TOKEN (a read-only personal access token) when it is set, so
language stats can include private repositories. Without it, falls back to
the workflow's GITHUB_TOKEN and public data only.

Private repository *names* never end up in an SVG: private repos only feed
aggregate numbers (language bytes, contribution totals).
"""

import html
import json
import os
import urllib.request
from collections import Counter
from pathlib import Path

USERNAME = os.getenv("USERNAME", "hieudepoet")
PAT = os.getenv("PROFILE_TOKEN", "").strip()
TOKEN = PAT or os.getenv("GITHUB_TOKEN", "")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "profile-readme-assets",
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"

ASSETS = Path("assets")
ASSETS.mkdir(exist_ok=True)

FONT = 'font-family="Inter, Segoe UI, Arial"'


def api_json(url, fallback):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception as exc:  # keep the workflow alive on API hiccups
        print(f"::warning::GET {url} failed: {exc}")
        return fallback


def graphql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={**HEADERS, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            payload = json.loads(res.read().decode("utf-8"))
    except Exception as exc:
        print(f"::warning::GraphQL request failed: {exc}")
        return {}
    if payload.get("errors"):
        print(f"::warning::GraphQL errors: {payload['errors']}")
    return payload.get("data") or {}


def esc(value):
    return html.escape(str(value), quote=True)


def fmt(n):
    n = int(n or 0)
    return f"{n/1000:.1f}k".replace(".0k", "k") if n >= 10000 else f"{n:,}"


def write(path, content):
    Path(path).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------- repos
def list_repos():
    repos, page = [], 1
    if PAT:
        base = "https://api.github.com/user/repos?visibility=all&affiliation=owner,collaborator,organization_member"
    else:
        base = f"https://api.github.com/users/{USERNAME}/repos?type=owner"
    while page <= 10:
        chunk = api_json(f"{base}&per_page=100&page={page}&sort=updated", [])
        if not isinstance(chunk, list) or not chunk:
            break
        repos.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return [r for r in repos if not r.get("fork") and not r.get("archived")]


repos = list_repos()
private_count = sum(1 for r in repos if r.get("private"))
print(f"repos: {len(repos)} ({private_count} private), PAT={'yes' if PAT else 'no'}")

# ---------------------------------------------------------------- languages
LANG_COLORS = {
    "TypeScript": "3178c6", "JavaScript": "f7df1e", "HTML": "e34c26",
    "CSS": "663399", "Java": "b07219", "C++": "00599c", "C": "555555",
    "Python": "3776ab", "Move": "6C63FF", "Shell": "89e051",
    "Dockerfile": "384d54", "MDX": "1f6feb", "Rust": "dea584", "Go": "00add8",
}
IGNORED_LANGS = {"HTML", "CSS", "SCSS", "Jupyter Notebook"}  # markup skews byte counts

lang_bytes = Counter()
for repo in repos[:150]:
    langs = api_json(repo["languages_url"], {}) if repo.get("languages_url") else {}
    if isinstance(langs, dict):
        lang_bytes.update({k: v for k, v in langs.items() if k not in IGNORED_LANGS})

total_lang = sum(lang_bytes.values()) or 1
top_langs = lang_bytes.most_common(8)

bars = []
for i, (lang, count) in enumerate(top_langs):
    pct = count / total_lang * 100
    color = LANG_COLORS.get(lang, "6C63FF")
    text_color = "111827" if color.lower() == "f7df1e" else "ffffff"
    bars.append(
        f'<g transform="translate(0,{i*36})">'
        f'<rect width="760" height="28" rx="14" fill="#0f172a"/>'
        f'<rect width="{max(12, min(760, pct*7.6)):.1f}" height="28" rx="14" fill="#{color}"/>'
        f'<text x="18" y="19" {FONT} font-size="13" font-weight="700" fill="#{text_color}">{esc(lang)}</text>'
        f'<text x="742" y="19" {FONT} font-size="13" font-weight="700" text-anchor="end" fill="#e5e7eb">{pct:.1f}%</text>'
        f"</g>"
    )
if not bars:
    bars.append(f'<text x="20" y="30" {FONT} font-size="16" fill="#e5e7eb">Language data will appear on the next run.</text>')

scope = f"{len(repos)} repos incl. {private_count} private" if private_count else f"{len(repos)} public repos"
lang_h = max(120, 70 + len(top_langs) * 36)
write(
    ASSETS / "language-badges.svg",
    f'''<svg width="800" height="{lang_h}" viewBox="0 0 800 {lang_h}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Language footprint">
<rect width="800" height="{lang_h}" rx="22" fill="#020617"/>
<text x="28" y="38" {FONT} font-size="22" font-weight="800" fill="#ffffff">Language footprint</text>
<text x="772" y="38" {FONT} font-size="13" font-weight="600" text-anchor="end" fill="#94a3b8">By code size · {esc(scope)}</text>
<g transform="translate(20,62)">{''.join(bars)}</g>
</svg>''',
)

# ---------------------------------------------------------------- activity (last 12 months)
data = graphql(
    """
    query($login: String!) {
      user(login: $login) {
        name
        contributionsCollection {
          contributionCalendar { totalContributions }
          totalCommitContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
          totalIssueContributions
          restrictedContributionsCount
        }
        repositoriesContributedTo(first: 1, includeUserRepositories: true,
          contributionTypes: [COMMIT, PULL_REQUEST, PULL_REQUEST_REVIEW, ISSUE]) { totalCount }
        pinnedItems(first: 6, types: REPOSITORY) {
          nodes { ... on Repository {
            name description url isPrivate stargazerCount forkCount
            primaryLanguage { name color }
            repositoryTopics(first: 3) { nodes { topic { name } } }
          } }
        }
      }
    }
    """,
    {"login": USERNAME},
)
user = data.get("user") or {}
cc = user.get("contributionsCollection") or {}
restricted = cc.get("restrictedContributionsCount") or 0

cards = [
    ("Contributions", (cc.get("contributionCalendar") or {}).get("totalContributions")),
    ("Commits", cc.get("totalCommitContributions")),
    ("Pull requests", cc.get("totalPullRequestContributions")),
    ("Code reviews", cc.get("totalPullRequestReviewContributions")),
    ("Repos touched", (user.get("repositoriesContributedTo") or {}).get("totalCount")),
]
card_svg = []
for i, (label, value) in enumerate(cards):
    x = 24 + i * 152
    card_svg.append(
        f'<g transform="translate({x},84)">'
        f'<rect width="140" height="92" rx="18" fill="#0f172a" stroke="#1e293b"/>'
        f'<text x="70" y="44" {FONT} font-size="28" font-weight="800" text-anchor="middle" fill="#22d3ee">{esc(fmt(value))}</text>'
        f'<text x="70" y="70" {FONT} font-size="13" font-weight="700" text-anchor="middle" fill="#cbd5e1">{esc(label)}</text>'
        f"</g>"
    )
note = f"Last 12 months · incl. {fmt(restricted)} private contributions" if restricted else "Last 12 months"
write(
    ASSETS / "github-summary.svg",
    f'''<svg width="800" height="220" viewBox="0 0 800 220" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="GitHub activity in the last 12 months">
<rect width="800" height="220" rx="22" fill="#020617"/>
<text x="28" y="42" {FONT} font-size="24" font-weight="800" fill="#ffffff">GitHub command center</text>
<text x="28" y="66" {FONT} font-size="14" fill="#94a3b8">{esc(user.get("name") or USERNAME)} · @{esc(USERNAME)} · {esc(note)}</text>
{''.join(card_svg)}
<text x="400" y="204" {FONT} font-size="12" text-anchor="middle" fill="#64748b">Generated daily by GitHub Actions.</text>
</svg>''',
)

# ---------------------------------------------------------------- featured (pinned, public only)
featured = []
for node in (user.get("pinnedItems") or {}).get("nodes") or []:
    if node and not node.get("isPrivate"):
        featured.append({
            "name": node["name"],
            "description": node.get("description"),
            "stars": node.get("stargazerCount", 0),
            "forks": node.get("forkCount", 0),
            "lang": (node.get("primaryLanguage") or {}).get("name"),
            "color": ((node.get("primaryLanguage") or {}).get("color") or "#6C63FF").lstrip("#"),
            "topics": [t["topic"]["name"] for t in (node.get("repositoryTopics") or {}).get("nodes") or []],
        })
if not featured:  # nothing pinned: fall back to most-starred public repos
    public = sorted(
        (r for r in repos if not r.get("private")),
        key=lambda r: (r.get("stargazers_count") or 0, r.get("updated_at") or ""),
        reverse=True,
    )
    for r in public[:4]:
        featured.append({
            "name": r["name"], "description": r.get("description"),
            "stars": r.get("stargazers_count", 0), "forks": r.get("forks_count", 0),
            "lang": r.get("language"), "color": LANG_COLORS.get(r.get("language") or "", "6C63FF"),
            "topics": (r.get("topics") or [])[:3],
        })
featured = featured[:4]

rows = []
for i, repo in enumerate(featured):
    y = 76 + i * 62
    desc = (repo["description"] or "No description yet.")
    desc = desc if len(desc) <= 84 else desc[:81] + "..."
    meta = " · ".join(filter(None, [repo["lang"], *repo["topics"]]))
    rows.append(
        f'<g transform="translate(28,{y})">'
        f'<rect width="744" height="52" rx="14" fill="#0f172a" stroke="#1e293b"/>'
        f'<circle cx="20" cy="18" r="5" fill="#{esc(repo["color"])}"/>'
        f'<text x="32" y="23" {FONT} font-size="15" font-weight="800" fill="#ffffff">{esc(repo["name"])}</text>'
        f'<text x="16" y="42" {FONT} font-size="11" fill="#94a3b8">{esc(desc)}</text>'
        f'<text x="728" y="23" {FONT} font-size="11" text-anchor="end" fill="#64748b">{esc(meta)}</text>'
        f'<text x="728" y="42" {FONT} font-size="12" text-anchor="end" fill="#22d3ee">★ {repo["stars"]} · ⑂ {repo["forks"]}</text>'
        f"</g>"
    )
if not rows:
    rows.append(f'<text x="28" y="95" {FONT} font-size="15" fill="#cbd5e1">Pin repositories on your profile to feature them here.</text>')

feat_h = 96 + max(1, len(featured)) * 62
write(
    ASSETS / "featured-projects.svg",
    f'''<svg width="800" height="{feat_h}" viewBox="0 0 800 {feat_h}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Featured repositories">
<rect width="800" height="{feat_h}" rx="22" fill="#020617"/>
<text x="28" y="42" {FONT} font-size="24" font-weight="800" fill="#ffffff">Featured projects</text>
<text x="28" y="62" {FONT} font-size="13" fill="#94a3b8">Pinned on my profile.</text>
{''.join(rows)}
</svg>''',
)
print("assets written")
