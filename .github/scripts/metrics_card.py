"""Render an accurate GitHub metrics card (SVG) straight from the GitHub GraphQL API.

Usage: GH_TOKEN=... python3 metrics_card.py <login> <fonts_dir> <out.svg>
Every number on the card comes from the API call shown next to it; nothing is estimated.
"""
import base64
import datetime as dt
import json
import math
import sys
import urllib.request
from html import escape

LOGIN, FONTS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
TOKEN = __import__("os").environ["GH_TOKEN"]
IGNORED_LANGS = {"Dockerfile", "Makefile", "Procfile", "Batchfile"}


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]


# ── Profile ──────────────────────────────────────────────────────────────────
u = gql(
    """query($login:String!){user(login:$login){
      name login createdAt avatarUrl(size:128)
      followers{totalCount} following{totalCount}
      organizations{totalCount} starredRepositories{totalCount} watching{totalCount}
      pullRequests{totalCount} issues{totalCount} issueComments{totalCount}
      repositoriesContributedTo(includeUserRepositories:true,
        contributionTypes:[COMMIT,ISSUE,PULL_REQUEST,REPOSITORY,PULL_REQUEST_REVIEW]){totalCount}
      contributionsCollection{contributionYears}
    }}""",
    login=LOGIN,
)["user"]

# ── Public repositories you own (stars, forks, languages) ───────────────────
repos, cursor = [], None
while True:
    page = gql(
        """query($login:String!,$cursor:String){user(login:$login){
          repositories(first:100,after:$cursor,ownerAffiliations:OWNER,privacy:PUBLIC){
            totalCount pageInfo{hasNextPage endCursor}
            nodes{isFork stargazerCount forkCount
              languages(first:20){edges{size node{name color}}}}}}}""",
        login=LOGIN, cursor=cursor,
    )["user"]["repositories"]
    repos += page["nodes"]
    if not page["pageInfo"]["hasNextPage"]:
        break
    cursor = page["pageInfo"]["endCursor"]
public_repos = page["totalCount"]
own = [r for r in repos if not r["isFork"]]
stars = sum(r["stargazerCount"] for r in own)
forks = sum(r["forkCount"] for r in own)
lang_bytes, lang_color = {}, {}
for r in own:
    for e in r["languages"]["edges"]:
        n = e["node"]["name"]
        if n in IGNORED_LANGS:
            continue
        lang_bytes[n] = lang_bytes.get(n, 0) + e["size"]
        lang_color[n] = e["node"]["color"] or "#8b949e"
total_bytes = sum(lang_bytes.values()) or 1
top_langs = sorted(lang_bytes.items(), key=lambda kv: -kv[1])[:8]

# ── Contributions, every year since joining ─────────────────────────────────
years = sorted(u["contributionsCollection"]["contributionYears"])
commits = private = reviews = 0
days = []
for y in years:
    c = gql(
        """query($login:String!,$from:DateTime!,$to:DateTime!){user(login:$login){
          contributionsCollection(from:$from,to:$to){
            totalCommitContributions restrictedContributionsCount totalPullRequestReviewContributions
            contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}""",
        login=LOGIN, **{"from": f"{y}-01-01T00:00:00Z", "to": f"{y}-12-31T23:59:59Z"},
    )["user"]["contributionsCollection"]
    commits += c["totalCommitContributions"]
    private += c["restrictedContributionsCount"]
    reviews += c["totalPullRequestReviewContributions"]
    days += [d for w in c["contributionCalendar"]["weeks"] for d in w["contributionDays"]]

today = dt.date.today().isoformat()
cal = {d["date"]: d["contributionCount"] for d in days if d["date"] <= today}
dates = sorted(cal)
best = run = 0
for d in dates:
    run = run + 1 if cal[d] else 0
    best = max(best, run)
current, i = 0, len(dates) - 1
if i >= 0 and cal[dates[i]] == 0:  # today not counted yet doesn't break the streak
    i -= 1
while i >= 0 and cal[dates[i]]:
    current, i = current + 1, i - 1
last_year = dates[-365:]
year_total = sum(cal[d] for d in last_year)
peak = max(cal[d] for d in last_year)
avg = year_total / len(last_year)

# ── Drawing helpers ──────────────────────────────────────────────────────────
W = 720
BG, PANEL, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, MUTED, ACCENT, CYAN = "#e6edf3", "#8b949e", "#BD93F9", "#8BE9FD"
out = []


def text(x, y, s, size=13, color=TEXT, weight=400, anchor="start"):
    out.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" '
               f'text-anchor="{anchor}">{escape(str(s))}</text>')


def fmt(n):
    return f"{n:,}"


def stat_block(x, y, title, rows):
    text(x, y, title, 15, ACCENT, 700)
    for k, (value, label) in enumerate(rows):
        yy = y + 26 + k * 22
        text(x, yy, fmt(value) if isinstance(value, int) else value, 14, TEXT, 700)
        text(x + 62, yy, label, 13, MUTED)


# ── Header ───────────────────────────────────────────────────────────────────
with urllib.request.urlopen(u["avatarUrl"], timeout=30) as r:
    avatar = base64.b64encode(r.read()).decode()
joined = dt.date.fromisoformat(u["createdAt"][:10])
years_on = (dt.date.today() - joined).days // 365
out.append('<clipPath id="av"><circle cx="58" cy="58" r="32"/></clipPath>')
out.append(f'<image href="data:image/png;base64,{avatar}" x="26" y="26" width="64" height="64" clip-path="url(#av)"/>')
out.append(f'<circle cx="58" cy="58" r="32" fill="none" stroke="{ACCENT}" stroke-width="2"/>')
text(106, 52, u["name"] or u["login"], 24, TEXT, 700)
text(106, 76, f'@{u["login"]} · joined GitHub {years_on} years ago · '
     f'{fmt(u["followers"]["totalCount"])} followers · {fmt(u["following"]["totalCount"])} following', 13, MUTED)
out.append(f'<line x1="24" y1="110" x2="{W-24}" y2="110" stroke="{BORDER}"/>')

# ── Stat columns ─────────────────────────────────────────────────────────────
stat_block(24, 140, "Activity (all time)", [
    (commits, "public commits"),
    (private, "private contributions"),
    (u["pullRequests"]["totalCount"], "pull requests opened"),
    (reviews, "pull requests reviewed"),
    (u["issues"]["totalCount"], "issues opened"),
])
stat_block(264, 140, "Repositories", [
    (public_repos, "public repositories"),
    (stars, "stars earned"),
    (forks, "forks of my repos"),
    (u["repositoriesContributedTo"]["totalCount"], "repos contributed to"),
    (u["issueComments"]["totalCount"], "issue comments"),
])
stat_block(504, 140, "Community", [
    (u["organizations"]["totalCount"], "organizations"),
    (u["starredRepositories"]["totalCount"], "repos starred"),
    (u["watching"]["totalCount"], "repos watched"),
    (u["followers"]["totalCount"], "followers"),
    (u["following"]["totalCount"], "following"),
])

# ── Languages ────────────────────────────────────────────────────────────────
y0 = 290
text(24, y0, "Most used languages", 15, ACCENT, 700)
text(W - 24, y0, "by code size across my public repos", 12, MUTED, anchor="end")
bar_w, x = W - 48, 24.0
out.append(f'<clipPath id="bar"><rect x="24" y="{y0+14}" width="{bar_w}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">')
for name, b in top_langs:
    w = bar_w * b / total_bytes
    out.append(f'<rect x="{x:.2f}" y="{y0+14}" width="{w+0.5:.2f}" height="10" fill="{lang_color[name]}"/>')
    x += w
out.append(f'<rect x="{x:.2f}" y="{y0+14}" width="{24+bar_w-x:.2f}" height="10" fill="{BORDER}"/></g>')
for k, (name, b) in enumerate(top_langs):
    lx, ly = 24 + (k % 4) * 168, y0 + 46 + (k // 4) * 22
    out.append(f'<circle cx="{lx+5}" cy="{ly-4}" r="5" fill="{lang_color[name]}"/>')
    text(lx + 16, ly, name, 13, TEXT, 500)
    text(lx + 150, ly, f"{100*b/total_bytes:.1f}%", 12, MUTED, anchor="end")

# ── 3D contribution calendar (last 26 weeks) ─────────────────────────────────
y1 = 400
text(24, y1, "Contributions calendar", 15, ACCENT, 700)
text(24, y1 + 18, "last 26 weeks, public + private", 12, MUTED)
end = dt.date.fromisoformat(dates[-1])
start = end - dt.timedelta(days=end.isoweekday() % 7 + 25 * 7)  # a Sunday, 26 weeks back
shades = ["#21262d", "#0e4429", "#006d32", "#26a641", "#39d353"]
window = [start + dt.timedelta(days=n) for n in range((end - start).days + 1)]
vmax = max([cal.get(d.isoformat(), 0) for d in window] + [1])
s, cw, ch = 9, 9 * math.cos(math.radians(30)), 9 * 0.5
ox, oy = 24 + 7 * cw + 6, y1 + 46
cells = []
for n, d in enumerate(window):
    wk, wd = n // 7, n % 7
    v = cal.get(d.isoformat(), 0)
    lvl = 0 if v == 0 else min(4, 1 + int(3 * v / vmax + 0.5))
    cells.append((wk + wd, wk, wd, v, lvl))
for _, wk, wd, v, lvl in sorted(cells):
    px, py = ox + (wk - wd) * cw, oy + (wk + wd) * ch
    h = 2 + 46 * v / vmax
    top = f"{px},{py-h} {px+cw},{py+ch-h} {px},{py+2*ch-h} {px-cw},{py+ch-h}"
    left = f"{px-cw},{py+ch-h} {px},{py+2*ch-h} {px},{py+2*ch} {px-cw},{py+ch}"
    right = f"{px+cw},{py+ch-h} {px},{py+2*ch-h} {px},{py+2*ch} {px+cw},{py+ch}"
    c = shades[lvl]
    out.append(f'<polygon points="{top}" fill="{c}"/>'
               f'<polygon points="{left}" fill="{c}" filter="url(#d1)"/>'
               f'<polygon points="{right}" fill="{c}" filter="url(#d2)"/>')

sx = 430
stat_block(sx, y1, "Contribution streaks", [
    (current, "days, current streak"),
    (best, "days, best streak ever"),
])
stat_block(sx, y1 + 92, "Last 12 months", [
    (year_total, "contributions"),
    (peak, "highest in one day"),
    (f"~{avg:.1f}", "per day on average"),
])
H = y1 + 230

# ── Assemble ─────────────────────────────────────────────────────────────────
faces = "".join(
    "@font-face{font-family:'Space Grotesk';font-weight:%s;src:url(data:font/woff2;base64,%s) format('woff2')}"
    % (w, base64.b64encode(open(f"{FONTS}/{w}.woff2", "rb").read()).decode())
    for w in (400, 500, 700))
svg = (
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
    f'role="img" aria-label="GitHub metrics for {escape(LOGIN)}">'
    f"<style>{faces}text{{font-family:'Space Grotesk',-apple-system,'Segoe UI',Helvetica,Arial,sans-serif}}</style>"
    '<filter id="d1"><feComponentTransfer><feFuncR type="linear" slope=".75"/><feFuncG type="linear" slope=".75"/>'
    '<feFuncB type="linear" slope=".75"/></feComponentTransfer></filter>'
    '<filter id="d2"><feComponentTransfer><feFuncR type="linear" slope=".55"/><feFuncG type="linear" slope=".55"/>'
    '<feFuncB type="linear" slope=".55"/></feComponentTransfer></filter>'
    f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="14" fill="{BG}" stroke="{BORDER}"/>'
    + "".join(out) + "</svg>"
)
open(OUT, "w", encoding="utf-8").write(svg)
print(f"wrote {OUT}: {public_repos} repos, {stars} stars, {forks} forks, {commits} commits, "
      f"{len(top_langs)} languages, streak {current}/{best}")
