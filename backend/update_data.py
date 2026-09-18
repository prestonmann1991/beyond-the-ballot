#!/usr/bin/env python3
"""Refresh State of the Races' public Oregon election data feed."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import html
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import re
from threading import Lock
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "backend" / "candidates_source.json"
RACES_PATH = ROOT / "backend" / "races_source.json"
OUTPUT_PATH = ROOT / "data" / "candidates.json"
HISTORY_PATH = ROOT / "data" / "snapshots.json"
CHECKPOINT_PATH = ROOT / "data" / "update_checkpoint.json"
BUNDLED_PATH = ROOT / "BeyondTheBallot" / "candidates.json"
CONFIGURATION_PATH = ROOT / "BeyondTheBallot" / "Configuration.swift"

ORESTAR_ROOT = "https://secure.sos.state.or.us/orestar/"
ACCOUNT_URL = ORESTAR_ROOT + "publicAccountSummary.do?filerId={}"
TRANSACTION_SEARCH_URL = ORESTAR_ROOT + "gotoPublicTransactionSearch.do"
TRANSACTION_RESULTS_URL = ORESTAR_ROOT + "gotoPublicTransactionSearchResults.do"
CSRF_TOKEN_URL = ORESTAR_ROOT + "JavaScriptServlet"
REGISTRATION_URL = "https://data.oregon.gov/resource/8h6y-5uec.json?$order=date%20DESC&$limit=5000"
REGISTRATION_SOURCE_URL = "https://data.oregon.gov/Administrative/Voter-Registration-Data/8h6y-5uec"
PACIFIC = ZoneInfo("America/Los_Angeles")
USER_AGENT = "StateOfTheRaces/1.1 (public election data updater; github.com/prestonmann1991/beyond-the-ballot)"
ORESTAR_MIN_INTERVAL_SECONDS = 2.0
ORESTAR_RETRY_DELAYS = (10, 30, 60)
DETAIL_RECOVERY_BATCH_SIZE = 12
_orestar_rate_lock = Lock()
_last_orestar_request = 0.0


def wait_for_orestar_slot(url: str) -> None:
    """Space public ORESTAR requests across all updater threads."""
    if not url.startswith(ORESTAR_ROOT):
        return
    global _last_orestar_request
    with _orestar_rate_lock:
        remaining = ORESTAR_MIN_INTERVAL_SECONDS - (time.monotonic() - _last_orestar_request)
        if remaining > 0:
            time.sleep(remaining)
        _last_orestar_request = time.monotonic()


def retry_wait_seconds(error: Exception, attempt: int) -> float:
    if isinstance(error, HTTPError) and error.code in (403, 429):
        retry_after = error.headers.get("Retry-After") if error.headers else None
        if retry_after:
            try:
                return max(float(retry_after), ORESTAR_RETRY_DELAYS[min(attempt, len(ORESTAR_RETRY_DELAYS) - 1)])
            except ValueError:
                pass
        return ORESTAR_RETRY_DELAYS[min(attempt, len(ORESTAR_RETRY_DELAYS) - 1)]
    return 2 * (attempt + 1)


def request(url: str, data: bytes | None = None, attempts: int = 4) -> str:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            wait_for_orestar_slot(url)
            req = Request(url, data=data, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=60) as response:
                return response.read().decode("utf-8", "replace")
        except (HTTPError, URLError, TimeoutError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(retry_wait_seconds(error, attempt))
    raise RuntimeError(str(last_error))


def opener_text(opener, req: Request, attempts: int = 4) -> str:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            wait_for_orestar_slot(req.full_url)
            with opener.open(req, timeout=60) as response:
                return response.read().decode("utf-8", "replace")
        except (HTTPError, URLError, TimeoutError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(retry_wait_seconds(error, attempt))
    raise RuntimeError(str(last_error))


def money(value: str) -> float:
    value = html.unescape(value).strip()
    negative = (value.startswith("(") and value.endswith(")")) or value.startswith("-")
    number = float(re.sub(r"[^0-9.]", "", value) or 0)
    return -number if negative else number


def clean_cell(value: str) -> str:
    value = re.sub(r"<script.*?</script>|<style.*?</style>", "", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(value).replace("\xa0", " ").split())


def table_rows(page: str) -> list[list[str]]:
    rows = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", page, flags=re.I | re.S):
        cells = [clean_cell(cell) for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, flags=re.I | re.S)]
        if cells:
            rows.append(cells)
    return rows


def parse_account_page(page: str) -> dict[str, float]:
    found: dict[str, float] = {}
    labels = {
        "Total Contributions": "contributionsYTD",
        "Total Expenditures": "expendituresYTD",
        "Balance Deficit": "balanceDeficit",
    }
    for cells in table_rows(page):
        label = cells[0].strip()
        if label in labels and labels[label] not in found:
            amount_cell = next((cell for cell in reversed(cells) if "$" in cell), None)
            if amount_cell:
                found[labels[label]] = money(amount_cell)
    missing = set(labels.values()) - found.keys()
    if missing:
        raise ValueError(f"Missing fields: {', '.join(sorted(missing))}")
    return found


def parse_transactions(page: str) -> list[dict]:
    transactions = []
    for cells in table_rows(page):
        if len(cells) < 7 or not cells[0].isdigit():
            continue
        try:
            parsed_date = datetime.strptime(cells[1], "%m/%d/%Y").date().isoformat()
        except ValueError:
            parsed_date = cells[1]
        transactions.append({
            "id": cells[0],
            "date": parsed_date,
            "name": re.sub(r"\s*\*\*\s*$", "", cells[4]).strip() or "Not reported",
            "category": cells[5] or "Not reported",
            "amount": money(cells[6]),
        })
    return transactions


def next_page_url(page: str) -> str | None:
    match = re.search(
        r'window\.location=["\']([^"\']*cneSearchButtonName=next[^"\']*)',
        page,
        flags=re.I,
    )
    return urljoin(ORESTAR_ROOT, html.unescape(match.group(1))) if match else None


def parse_filed_at(page: str) -> str:
    for cells in table_rows(page):
        for index, cell in enumerate(cells):
            if cell.strip() != "Filed Date":
                continue
            for value in cells[index + 1:]:
                if value == ":":
                    continue
                for date_format in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y"):
                    try:
                        return datetime.strptime(value, date_format).isoformat(timespec="seconds")
                    except ValueError:
                        pass
    raise ValueError("ORESTAR transaction filed date was not found")


def parse_filed_date(page: str) -> str:
    return parse_filed_at(page)[:10]


def form_action(page: str) -> str:
    match = re.search(
        r'<form\b[^>]*name=["\']cneSearchForm["\'][^>]*action=["\']([^"\']+)',
        page,
        flags=re.I,
    )
    if not match:
        raise ValueError("ORESTAR transaction-search form action was not found")
    return urljoin(TRANSACTION_SEARCH_URL, html.unescape(match.group(1)))


def csrf_token(opener) -> tuple[str, str]:
    req = Request(
        CSRF_TOKEN_URL,
        data=b"",
        headers={"User-Agent": USER_AGENT, "FETCH-CSRF-TOKEN": "1"},
    )
    pair = opener_text(opener, req).strip()
    if ":" not in pair:
        raise ValueError("ORESTAR transaction-search token was not returned")
    name, value = pair.split(":", 1)
    if not name or not value:
        raise ValueError("ORESTAR transaction-search token was incomplete")
    return name, value


def hidden_fields(page: str) -> dict[str, str]:
    fields = {}
    for tag in re.findall(r"<input\b[^>]*>", page, flags=re.I):
        if not re.search(r'type=["\']hidden["\']', tag, flags=re.I):
            continue
        name = re.search(r'name=["\']([^"\']+)', tag, flags=re.I)
        value = re.search(r'value=["\']([^"\']*)', tag, flags=re.I)
        if name:
            fields[html.unescape(name.group(1))] = html.unescape(value.group(1)) if value else ""
    return fields


def fetch_transaction_pages(
    opener,
    action_url: str,
    base_fields: dict[str, str],
    filer_id: int,
    transaction_type: str,
    date_fields: dict[str, str] | None = None,
) -> list[dict]:
    type_name = "Contribution" if transaction_type == "C" else "Expenditure"
    fields = dict(base_fields)
    fields.update({
        "cneSearchButtonName": "search",
        "cneSearchPageIdx": "0",
        "cneSearchFilerCommitteeId": str(filer_id),
        "cneSearchTranType": transaction_type,
        "cneSearchTranTypeName": type_name,
    })
    fields.update(date_fields or {})
    req = Request(
        action_url,
        data=urlencode(fields).encode(),
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": TRANSACTION_SEARCH_URL,
        },
    )
    page = opener_text(opener, req)
    transactions: list[dict] = []
    seen_ids: set[str] = set()
    while True:
        page_transactions = parse_transactions(page)
        new_transactions = [item for item in page_transactions if item["id"] not in seen_ids]
        if not new_transactions:
            break
        transactions.extend(new_transactions)
        seen_ids.update(item["id"] for item in new_transactions)
        next_url = next_page_url(page)
        if not next_url:
            break
        page = opener_text(opener, Request(next_url, headers={"User-Agent": USER_AGENT, "Referer": action_url}))
    return transactions


def add_filed_dates(opener, transactions: list[dict], cached: list[dict]) -> list[dict]:
    cached_dates = {item["id"]: item.get("filedDate") for item in cached if item.get("filedDate")}
    cached_times = {item["id"]: item.get("filedAt") for item in cached if item.get("filedAt")}
    output = []
    for transaction in transactions:
        item = dict(transaction)
        filed_date = cached_dates.get(item["id"])
        filed_at = cached_times.get(item["id"])
        if not filed_date or not filed_at:
            detail_url = urljoin(ORESTAR_ROOT, f"gotoPublicTransactionDetail.do?tranRsn={item['id']}")
            filed_at = parse_filed_at(
                opener_text(opener, Request(detail_url, headers={"User-Agent": USER_AGENT}))
            )
            filed_date = filed_at[:10]
        item["filedDate"] = filed_date
        item["filedAt"] = filed_at
        output.append(item)
    return sorted(output, key=lambda item: (item["filedAt"], int(item["id"])), reverse=True)


def aggregate_top_contributors(transactions: list[dict], limit: int = 10) -> list[dict]:
    totals: dict[str, dict] = {}
    for transaction in transactions:
        name = " ".join(transaction.get("name", "Not reported").split()) or "Not reported"
        key = name.casefold()
        if key not in totals:
            totals[key] = {"name": name, "amount": 0.0}
        totals[key]["amount"] += transaction.get("amount", 0)
    ranked = sorted(totals.values(), key=lambda item: (-item["amount"], item["name"].casefold()))
    return [{"name": item["name"], "amount": round(item["amount"], 2)} for item in ranked[:limit]]


def top_contributors_need_refresh(summary: dict, previous: dict) -> bool:
    return (
        summary.get("contributionsYTD") != previous.get("contributionsYTD")
        or "topContributorsSince2026" not in previous
        or previous.get("financeDetailsPending") is True
        or str(previous.get("dataError", "")).startswith("Refresh failed:")
    )


def reported_transaction_types_to_refresh(summary: dict, previous: dict) -> set[str]:
    refresh = set()
    if (
        summary.get("contributionsYTD") != previous.get("contributionsYTD")
        or "reportedContributions7Days" not in previous
        or previous.get("financeDetailsPending") is True
        or str(previous.get("dataError", "")).startswith("Refresh failed:")
    ):
        refresh.add("C")
    if (
        summary.get("expendituresYTD") != previous.get("expendituresYTD")
        or "reportedExpenditures7Days" not in previous
        or previous.get("financeDetailsPending") is True
        or str(previous.get("dataError", "")).startswith("Refresh failed:")
    ):
        refresh.add("E")
    return refresh


def retain_filed_since(transactions: list[dict], cutoff) -> list[dict]:
    return [item for item in transactions if item.get("filedDate", "") >= cutoff.isoformat()]


def fetch_candidate(
    candidate: dict,
    previous: dict | None = None,
    now: datetime | None = None,
    refresh_details: bool = True,
) -> dict:
    item = dict(candidate)
    previous = previous or {}
    now = now or datetime.now(PACIFIC)
    filer_id = item.get("filerID")
    item["orestarURL"] = ACCOUNT_URL.format(filer_id) if filer_id else None
    if not filer_id:
        item.update({
            "contributionsYTD": None,
            "expendituresYTD": None,
            "balanceDeficit": None,
            "recentContributions": [],
            "recentExpenditures": [],
            "reportedContributions7Days": [],
            "reportedExpenditures7Days": [],
            "topContributorsSince2026": [],
            "financeDetailsPending": False,
            "dataError": "ORESTAR committee not yet linked",
        })
        return item
    summary = parse_account_page(request(ACCOUNT_URL.format(filer_id)))
    item.update(summary)
    item["recentContributions"] = previous.get("recentContributions", [])
    item["recentExpenditures"] = previous.get("recentExpenditures", [])
    seven_days_ago = now.date() - timedelta(days=7)
    item["reportedContributions7Days"] = retain_filed_since(
        previous.get("reportedContributions7Days", []), seven_days_ago
    )
    item["reportedExpenditures7Days"] = retain_filed_since(
        previous.get("reportedExpenditures7Days", []), seven_days_ago
    )
    item["topContributorsSince2026"] = previous.get("topContributorsSince2026", [])

    refresh_types = reported_transaction_types_to_refresh(summary, previous)
    refresh_top = top_contributors_need_refresh(summary, previous)
    if (refresh_types or refresh_top) and not refresh_details:
        item["financeDetailsPending"] = True
        item["dataError"] = None
        return item
    if refresh_types or refresh_top:
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        search_page = opener_text(opener, Request(TRANSACTION_SEARCH_URL, headers={"User-Agent": USER_AGENT}))
        fields = hidden_fields(search_page)
        token_name, token_value = csrf_token(opener)
        fields[token_name] = token_value
        action_url = form_action(search_page)

    filed_range = {
        "cneSearchTranFiledStartDate": seven_days_ago.strftime("%m/%d/%Y"),
        "cneSearchTranFiledEndDate": now.date().strftime("%m/%d/%Y"),
    }
    for transaction_type, field_name in (
        ("C", "reportedContributions7Days"),
        ("E", "reportedExpenditures7Days"),
    ):
        if transaction_type not in refresh_types:
            continue
        transactions = fetch_transaction_pages(
            opener, action_url, fields, filer_id, transaction_type, filed_range
        )
        item[field_name] = add_filed_dates(opener, transactions, previous.get(field_name, []))

    # Preserve the legacy fields while version 1.0 remains installable.
    item["recentContributions"] = item["reportedContributions7Days"][:10]
    item["recentExpenditures"] = item["reportedExpenditures7Days"][:10]

    if refresh_top:
        transaction_range = {
            "cneSearchTranStartDate": "01/01/2026",
            "cneSearchTranEndDate": now.date().strftime("%m/%d/%Y"),
        }
        contributions = fetch_transaction_pages(
            opener, action_url, fields, filer_id, "C", transaction_range
        )
        item["topContributorsSince2026"] = aggregate_top_contributors(contributions)
    item["financeDetailsPending"] = False
    item["dataError"] = None
    return item


def detail_recovery_ids(
    candidates: list[dict], previous_candidates: dict[str, dict], limit: int = DETAIL_RECOVERY_BATCH_SIZE
) -> set[str]:
    """Select a small, deterministic batch of interrupted detail migrations."""
    pending = []
    for candidate in candidates:
        previous = previous_candidates.get(candidate["id"], {})
        if (
            previous.get("financeDetailsPending") is True
            or str(previous.get("dataError", "")).startswith("Refresh failed:")
        ):
            pending.append(candidate["id"])
    return set(pending[:limit])


def latest_registration_rows() -> tuple[list[dict], str]:
    rows = json.loads(request(REGISTRATION_URL))
    if not rows:
        raise ValueError("The Oregon registration dataset returned no rows")
    newest = max(row.get("date", "") for row in rows)
    return [row for row in rows if row.get("date") == newest], newest[:10]


def district_number(value: str) -> int | None:
    match = re.search(r"(\d+)\s*$", value or "")
    return int(match.group(1)) if match else None


def registration_for_races(races: list[dict], previous: dict[str, dict]) -> list[dict]:
    try:
        rows, as_of = latest_registration_rows()
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"Registration refresh failed: {error}")
        rows, as_of = [], ""

    output = []
    for race in races:
        item = dict(race)
        matching = []
        if rows:
            if item["name"] == "Oregon Governor":
                matching = rows
            elif item["name"].startswith("House District"):
                wanted = district_number(item["name"])
                matching = [row for row in rows if district_number(row.get("sr_desc", "")) == wanted]
            elif item["name"].startswith("Senate District"):
                wanted = district_number(item["name"])
                matching = [row for row in rows if district_number(row.get("ss_desc", "")) == wanted]

        totals = {"Democratic": 0, "Republican": 0, "Other": 0}
        for row in matching:
            count = int(float(row.get("sum_partycount", 0)))
            party = row.get("party", "")
            if party == "Democrat":
                totals["Democratic"] += count
            elif party == "Republican":
                totals["Republican"] += count
            else:
                totals["Other"] += count
        total = sum(totals.values())
        if total:
            item["registration"] = {
                "asOf": as_of,
                "democraticPct": round(100 * totals["Democratic"] / total, 1),
                "republicanPct": round(100 * totals["Republican"] / total, 1),
                "otherPct": round(100 * totals["Other"] / total, 1),
                "totalActive": total,
            }
        else:
            item["registration"] = previous.get(item["id"], {}).get("registration")
        item["registrationSourceURL"] = REGISTRATION_SOURCE_URL
        output.append(item)
    return output


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def add_ten_day_deltas(candidates: list[dict], history: list[dict], now: datetime) -> None:
    cutoff = now - timedelta(days=10)
    eligible = []
    for snapshot in history:
        try:
            captured = datetime.fromisoformat(snapshot["capturedAt"])
            if captured <= cutoff:
                eligible.append((captured, snapshot))
        except (KeyError, ValueError):
            continue
    baseline = max(eligible, key=lambda pair: pair[0])[1].get("candidates", {}) if eligible else {}
    for candidate in candidates:
        old = baseline.get(candidate["id"], {})
        for current_key, delta_key in (
            ("contributionsYTD", "contributionDelta10Days"),
            ("expendituresYTD", "expenditureDelta10Days"),
        ):
            current, prior = candidate.get(current_key), old.get(current_key)
            candidate[delta_key] = round(current - prior, 2) if current is not None and prior is not None else None


def update_history(history: list[dict], candidates: list[dict], now: datetime) -> list[dict]:
    snapshot = {
        "capturedAt": now.isoformat(timespec="seconds"),
        "candidates": {
            item["id"]: {
                "contributionsYTD": item.get("contributionsYTD"),
                "expendituresYTD": item.get("expendituresYTD"),
            }
            for item in candidates
        },
    }
    oldest = now - timedelta(days=120)
    retained = []
    for item in history:
        try:
            if datetime.fromisoformat(item["capturedAt"]) >= oldest:
                retained.append(item)
        except (KeyError, ValueError):
            pass
    return retained + [snapshot]


def refresh() -> int:
    repository_owner = os.getenv("GITHUB_REPOSITORY_OWNER")
    if repository_owner and CONFIGURATION_PATH.exists():
        configuration = CONFIGURATION_PATH.read_text()
        configured = configuration.replace("YOUR_GITHUB_USERNAME", repository_owner)
        if configured != configuration:
            CONFIGURATION_PATH.write_text(configured)

    source = read_json(SOURCE_PATH, {"candidates": []})
    race_source = read_json(RACES_PATH, {"races": []})
    previous_feed = read_json(OUTPUT_PATH, {})
    previous_candidates = {item["id"]: item for item in previous_feed.get("candidates", [])}
    checkpoint_candidates = read_json(CHECKPOINT_PATH, {})
    previous_candidates.update(checkpoint_candidates)
    previous_races = {item["id"]: item for item in previous_feed.get("races", [])}
    history = read_json(HISTORY_PATH, [])
    failures = 0
    refreshed_by_id: dict[str, dict] = dict(checkpoint_candidates)
    pending_ids = {
        candidate["id"]
        for candidate in source["candidates"]
        if previous_candidates.get(candidate["id"], {}).get("financeDetailsPending") is True
        or str(previous_candidates.get(candidate["id"], {}).get("dataError", "")).startswith("Refresh failed:")
    }
    recovery_ids = detail_recovery_ids(source["candidates"], previous_candidates)
    if pending_ids:
        print(
            f"Recovering detailed finance data for {len(recovery_ids)} of "
            f"{len(pending_ids)} pending candidates this run",
            flush=True,
        )

    total_candidates = len(source["candidates"])
    completed = len(checkpoint_candidates)
    if completed:
        print(f"Resuming from checkpoint: {completed}/{total_candidates} candidates complete", flush=True)
    migration_order = sorted(
        [item for item in source["candidates"] if item["id"] not in checkpoint_candidates],
        key=lambda item: previous_candidates.get(item["id"], {}).get("contributionsYTD") or 0,
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        futures = {
            pool.submit(
                fetch_candidate,
                candidate,
                previous_candidates.get(candidate["id"], {}),
                None,
                candidate["id"] not in pending_ids or candidate["id"] in recovery_ids,
            ): candidate
            for candidate in migration_order
        }
        for future in as_completed(futures):
            original = futures[future]
            try:
                item = future.result()
            except (RuntimeError, ValueError, HTTPError, URLError, TimeoutError) as error:
                failures += 1
                item = dict(original)
                old = previous_candidates.get(item["id"], {})
                item["orestarURL"] = ACCOUNT_URL.format(item["filerID"]) if item.get("filerID") else None
                for field in (
                    "contributionsYTD", "expendituresYTD", "balanceDeficit",
                    "recentContributions", "recentExpenditures",
                    "reportedContributions7Days", "reportedExpenditures7Days",
                    "topContributorsSince2026",
                ):
                    is_collection = field.startswith("recent") or field.startswith("reported") or field.startswith("top")
                    item[field] = old.get(field, [] if is_collection else None)
                item["financeDetailsPending"] = True
                item["dataError"] = None
            refreshed_by_id[item["id"]] = item
            if not item.get("financeDetailsPending"):
                checkpoint_candidates[item["id"]] = item
                CHECKPOINT_PATH.write_text(
                    json.dumps(checkpoint_candidates, indent=2, ensure_ascii=False) + "\n"
                )
            completed += 1
            status = item.get("dataError") or "complete"
            print(f"[{completed}/{total_candidates}] {item['name']}: {status}", flush=True)

    candidates = [refreshed_by_id[item["id"]] for item in source["candidates"]]
    now = datetime.now(PACIFIC)
    add_ten_day_deltas(candidates, history, now)
    races = registration_for_races(race_source["races"], previous_races)
    feed = {
        "updatedAt": now.isoformat(timespec="seconds"),
        "source": "Oregon Secretary of State ORESTAR and Oregon Elections Division",
        "races": races,
        "candidates": candidates,
    }

    encoded = json.dumps(feed, indent=2, ensure_ascii=False) + "\n"
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(encoded)
    BUNDLED_PATH.write_text(encoded)
    HISTORY_PATH.write_text(json.dumps(update_history(history, candidates, now), indent=2) + "\n")
    CHECKPOINT_PATH.unlink(missing_ok=True)
    print(f"Updated {len(candidates) - failures}/{len(candidates)} candidates; {failures} failures")
    return 1 if failures == len(candidates) else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduled", action="store_true", help=argparse.SUPPRESS)
    parser.parse_args()
    raise SystemExit(refresh())
