from datetime import datetime, timedelta
import json
from pathlib import Path
import unittest
from urllib.error import HTTPError

from backend.update_data import (
    add_ten_day_deltas,
    form_action,
    hidden_fields,
    money,
    parse_account_page,
    parse_transactions,
    retry_wait_seconds,
    transaction_types_to_refresh,
)


class OrestarParserTests(unittest.TestCase):
    def test_money(self):
        self.assertEqual(money("$1,234.56"), 1234.56)
        self.assertEqual(money("($42.00)"), -42.0)

    def test_account_summary(self):
        page = """
        <table>
          <tr><td><b>Total Contributions</b></td><td></td><td><b>$10,100.25</b></td></tr>
          <tr><td><b>Total Expenditures</b></td><td></td><td><b>$9,200.00</b></td></tr>
          <tr><td><b>Balance Deficit</b></td><td></td><td><b>($75.50)</b></td></tr>
        </table>
        """
        self.assertEqual(
            parse_account_page(page),
            {"contributionsYTD": 10100.25, "expendituresYTD": 9200.0, "balanceDeficit": -75.5},
        )

    def test_hidden_fields_omit_unchecked_controls(self):
        page = """
        <input type="hidden" name="page" value="0">
        <input type="checkbox" name="deleted" value="on">
        <input type="text" name="filer" value="">
        """
        self.assertEqual(hidden_fields(page), {"page": "0"})

    def test_transaction_form_action(self):
        page = '<form name="cneSearchForm" action="/orestar/results.do;SESSION=abc">'
        self.assertEqual(
            form_action(page),
            "https://secure.sos.state.or.us/orestar/results.do;SESSION=abc",
        )

    def test_transactions(self):
        page = """
        <table>
          <tr><th>Tran ID</th><th>Tran Date</th><th>Status</th><th>Filer</th><th>Contributor</th><th>Sub Type</th><th>Amount</th></tr>
          <tr><td>5806472</td><td>09/11/2026</td><td>Original</td><td>Committee</td><td>Jane Doe **</td><td>Cash Contribution</td><td>$100.00</td></tr>
        </table>
        """
        self.assertEqual(
            parse_transactions(page),
            [{
                "id": "5806472",
                "date": "2026-09-11",
                "name": "Jane Doe",
                "category": "Cash Contribution",
                "amount": 100.0,
            }],
        )

    def test_ten_day_delta_uses_latest_eligible_snapshot(self):
        now = datetime.fromisoformat("2026-09-15T12:00:00-07:00")
        history = [
            {
                "capturedAt": (now - timedelta(days=11)).isoformat(),
                "candidates": {"candidate": {"contributionsYTD": 100, "expendituresYTD": 40}},
            },
            {
                "capturedAt": (now - timedelta(days=10, hours=1)).isoformat(),
                "candidates": {"candidate": {"contributionsYTD": 120, "expendituresYTD": 50}},
            },
        ]
        candidates = [{"id": "candidate", "contributionsYTD": 175, "expendituresYTD": 80}]
        add_ten_day_deltas(candidates, history, now)
        self.assertEqual(candidates[0]["contributionDelta10Days"], 55)
        self.assertEqual(candidates[0]["expenditureDelta10Days"], 30)

    def test_rate_limit_errors_use_longer_backoff(self):
        forbidden = HTTPError("https://example.com", 403, "Forbidden", {}, None)
        too_many = HTTPError("https://example.com", 429, "Too Many Requests", {"Retry-After": "45"}, None)
        self.assertEqual(retry_wait_seconds(forbidden, 0), 10)
        self.assertEqual(retry_wait_seconds(forbidden, 1), 30)
        self.assertEqual(retry_wait_seconds(too_many, 0), 45)

    def test_transactions_refresh_only_when_changed_or_missing(self):
        summary = {"contributionsYTD": 150, "expendituresYTD": 80}
        complete = {
            "contributionsYTD": 150,
            "expendituresYTD": 80,
            "recentContributions": [{"id": "1"}],
            "recentExpenditures": [{"id": "2"}],
        }
        self.assertEqual(transaction_types_to_refresh(summary, complete), set())

        changed = dict(complete, contributionsYTD=125)
        self.assertEqual(transaction_types_to_refresh(summary, changed), {"C"})

        missing = dict(complete, recentExpenditures=[])
        self.assertEqual(transaction_types_to_refresh(summary, missing), {"E"})


class ElectionSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.races = json.loads((root / "backend" / "races_source.json").read_text())["races"]
        cls.candidates = json.loads((root / "backend" / "candidates_source.json").read_text())["candidates"]

    def test_all_2026_races_are_present(self):
        self.assertEqual(len([race for race in self.races if race["id"].startswith("hd")]), 60)
        self.assertEqual(len([race for race in self.races if race["id"].startswith("sd")]), 15)
        self.assertEqual(len(self.races), 76)

    def test_candidate_source_has_no_duplicates(self):
        identities = [(candidate["race"], candidate["name"]) for candidate in self.candidates]
        self.assertEqual(len(identities), 148)
        self.assertEqual(len(identities), len(set(identities)))

        filer_ids = [candidate["filerID"] for candidate in self.candidates if candidate.get("filerID")]
        self.assertEqual(len(filer_ids), 130)
        self.assertEqual(len(filer_ids), len(set(filer_ids)))

    def test_historical_election_years_match_product_rules(self):
        for race in self.races:
            years = [election["year"] for election in race["historicalElections"]]
            if race["id"] == "governor":
                self.assertEqual(years, [2022])
            elif race["id"].startswith("hd"):
                self.assertEqual(years, [2024, 2022])
            else:
                self.assertEqual(years, [2022])
            for election in race["historicalElections"]:
                self.assertGreater(len(election["results"]), 0)
                for result in election["results"]:
                    self.assertGreaterEqual(result["votes"], 0)
                    self.assertGreaterEqual(result["percentage"], 0)
                    self.assertLessEqual(result["percentage"], 100)


if __name__ == "__main__":
    unittest.main()
