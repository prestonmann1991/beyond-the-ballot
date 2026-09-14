#!/usr/bin/env python3
"""Refresh selected Oregon candidate account summaries from public ORESTAR pages."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "backend" / "candidates_source.json"
OUTPUT_PATH = ROOT / "data" / "candidates.json"
BUNDLED_PATH = ROOT / "BeyondTheBallot" / "candidates.json"
CONFIGURATION_PATH = ROOT / "BeyondTheBallot" / "Configuration.swift"
ORESTAR = "https://secure.sos.state.or.us/orestar/publicAccountSummary.do?filerId={}"
PACIFIC = ZoneInfo("America/Los_Angeles")


def money(value: str) -> float:
    value = html.unescape(value).strip()
    negative = value.startswith("(") and value.endswith(")")
    number = float(re.sub(r"[^0-9.]", "", value) or 0)
    return -number if negative else number


def clean_cell(value: str) -> str:
    value = re.sub(r"<script.*?</script>|<style.*?</style>", "", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(value).replace("\xa0", " ").split())


def parse_account_page(page: str) -> dict[str, float]:
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", page, flags=re.I | re.S)
    found: dict[str, float] = {}
    labels = {
        "Total Contributions": "contributionsYTD",
        "Total Expenditures": "expendituresYTD",
        "Balance Deficit": "balanceDeficit",
    }
    for row in rows:
        cells = [clean_cell(cell) for cell in re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.I | re.S)]
        if len(cells) < 2:
            continue
        label = cells[0].strip()
        if label in labels and labels[label] not in found:
            amount_cell = next((cell for cell in reversed(cells) if "$" in cell), None)
            if amount_cell:
                found[labels[label]] = money(amount_cell)
    missing = {"contributionsYTD", "expendituresYTD", "balanceDeficit"} - found.keys()
    if missing:
        raise ValueError(f"Missing fields: {', '.join(sorted(missing))}")
    return found


def fetch_account(filer_id: int, attempts: int = 3) -> dict[str, float]:
    request = Request(
        ORESTAR.format(filer_id),
        headers={"User-Agent": "BeyondTheBallot/1.0 (public election data updater)"},
    )
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=45) as response:
                return parse_account_page(response.read().decode("utf-8", "replace"))
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(str(last_error))


def refresh() -> int:
    repository_owner = os.getenv("GITHUB_REPOSITORY_OWNER")
    if repository_owner and CONFIGURATION_PATH.exists():
        configuration = CONFIGURATION_PATH.read_text()
        configured = configuration.replace("YOUR_GITHUB_USERNAME", repository_owner)
        if configured != configuration:
            CONFIGURATION_PATH.write_text(configured)

    source = json.loads(SOURCE_PATH.read_text())
    previous = {}
    if OUTPUT_PATH.exists():
        previous_feed = json.loads(OUTPUT_PATH.read_text())
        previous = {candidate["id"]: candidate for candidate in previous_feed.get("candidates", [])}

    failures = 0
    refreshed_by_id = {}

    def update_candidate(candidate: dict) -> dict:
        item = dict(candidate)
        item["orestarURL"] = ORESTAR.format(item["filerID"]) if item.get("filerID") else None
        try:
            if item.get("filerID"):
                item.update(fetch_account(item["filerID"]))
                item["dataError"] = None
            else:
                item.update({"contributionsYTD": None, "expendituresYTD": None, "balanceDeficit": None})
                item["dataError"] = "No ORESTAR committee reported"
        except RuntimeError as error:
            old = previous.get(item["id"], {})
            for field in ("contributionsYTD", "expendituresYTD", "balanceDeficit"):
                item[field] = old.get(field)
            item["dataError"] = f"Refresh failed: {error}"
        return item

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(update_candidate, candidate): candidate for candidate in source["candidates"]}
        for future in as_completed(futures):
            item = future.result()
            if (item.get("dataError") or "").startswith("Refresh failed"):
                failures += 1
            refreshed_by_id[item["id"]] = item

    refreshed = [refreshed_by_id[candidate["id"]] for candidate in source["candidates"]]

    feed = {
        "updatedAt": datetime.now(PACIFIC).isoformat(timespec="seconds"),
        "source": "Oregon Secretary of State ORESTAR",
        "candidates": refreshed,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(feed, indent=2, ensure_ascii=False) + "\n"
    OUTPUT_PATH.write_text(encoded)
    BUNDLED_PATH.write_text(encoded)
    print(f"Updated {len(refreshed) - failures}/{len(refreshed)} candidates; {failures} failures")
    return 1 if failures == len(refreshed) else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduled", action="store_true", help="Only refresh during the 6 a.m. Pacific hour")
    args = parser.parse_args()
    if args.scheduled and datetime.now(PACIFIC).hour != 6:
        print("Skipping: it is not 6 a.m. in America/Los_Angeles")
        raise SystemExit(0)
    raise SystemExit(refresh())
