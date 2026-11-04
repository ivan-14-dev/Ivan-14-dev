"""Render the account's all-time contribution totals from GitHub's GraphQL API."""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


USERNAME = "ivan-14-dev"
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "contributions.svg"


def graphql(query):
    result = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query}", "-f", f"login={USERNAME}"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    response = json.loads(result.stdout)
    if response.get("errors"):
        raise RuntimeError(f"GitHub GraphQL errors: {response['errors']}")
    if not response.get("data", {}).get("user"):
        raise RuntimeError("GitHub did not return the requested user.")
    return response["data"]["user"]


def collect_contributions(now):
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    user = graphql(
        "query($login: String!) { user(login: $login) { createdAt "
        "contributionsCollection { contributionYears } } }"
    )
    created = datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    years = user["contributionsCollection"]["contributionYears"]
    if (
        not isinstance(years, list)
        or any(type(year) is not int or not 1970 <= year <= now.year for year in years)
        or created > now
    ):
        raise ValueError("GitHub returned invalid contribution years.")

    # Include earlier attributed contributions as well as empty account years.
    years = sorted(set(years) | set(range(created.year, now.year + 1)))
    fields = []
    for year in years:
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = min(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc), now)
        fields.append(
            f'y{year}: contributionsCollection(from: "{start.isoformat()}", '
            f'to: "{end.isoformat()}") '
            "{ contributionCalendar { totalContributions } }"
        )
    user = graphql(
        "query($login: String!) { user(login: $login) { " + " ".join(fields) + " } }"
    )
    totals = {}
    for year in years:
        total = user[f"y{year}"]["contributionCalendar"]["totalContributions"]
        if type(total) is not int or total < 0:
            raise ValueError(f"GitHub returned an invalid total for {year}.")
        totals[year] = total
    return totals


def render_svg(totals, now):
    timestamp = now.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total = sum(totals.values())
    height = 280 + 38 * len(totals)
    rows = []
    for index, (year, count) in enumerate(sorted(totals.items())):
        y = 230 + index * 38
        period = "year to date" if year == now.year else "full calendar year"
        rows.append(
            f'    <text x="36" y="{y}" font-size="16" fill="#bfdbfe">'
            f'{year} ({period})</text>\n'
            f'    <text x="864" y="{y}" text-anchor="end" font-size="20" '
            f'font-weight="700" fill="#ffffff">{count:,}</text>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{height}" viewBox="0 0 900 {height}" role="img" aria-labelledby="title description">
  <title id="title">GitHub contributions: {total:,} as of {timestamp}</title>
  <desc id="description">All-time total reported by GitHub's contribution calendar, summed across calendar years. Only contributions visible to the API are included. Updated daily, not live.</desc>
  <defs>
    <linearGradient id="border" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#1e3a8a"/>
      <stop offset="1" stop-color="#60a5fa"/>
    </linearGradient>
  </defs>
  <rect x="1" y="1" width="898" height="{height - 2}" rx="20" fill="#0d1117" stroke="url(#border)" stroke-width="2"/>
  <g font-family="Arial, Helvetica, sans-serif">
    <text x="36" y="43" font-size="15" font-weight="700" letter-spacing="2" fill="#93c5fd">GITHUB CONTRIBUTIONS</text>
    <text x="34" y="122" font-size="68" font-weight="700" fill="#ffffff">{total:,}</text>
    <text x="36" y="151" font-size="16" fill="#bfdbfe">All-time total reported by GitHub</text>
    <text x="36" y="179" font-size="13" fill="#94a3b8">Updated: {timestamp}</text>
    <path d="M34 198 H866" stroke="#1e293b"/>
{chr(10).join(rows)}
    <path d="M34 {height - 63} H866" stroke="#1e293b"/>
    <text x="36" y="{height - 35}" font-size="13" fill="#94a3b8">Source: GitHub GraphQL contribution calendar. API-visible contributions only.</text>
    <text x="36" y="{height - 15}" font-size="12" fill="#94a3b8">Updated daily, not live. The profile's rolling-year graph covers a different period.</text>
  </g>
</svg>
"""


def main():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    totals = collect_contributions(now)
    OUTPUT.write_text(render_svg(totals, now), encoding="utf-8")
    print(f"Updated contributions: {sum(totals.values())} across {len(totals)} years.")


if __name__ == "__main__":
    main()
