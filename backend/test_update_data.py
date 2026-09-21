from datetime import date, datetime, timedelta
import json
from pathlib import Path
import unittest
from urllib.error import HTTPError

from backend.update_data import (
    add_ten_day_deltas,
    aggregate_top_contributors,
    candidate_from_collective_data,
    detail_recovery_ids,
    filer_id_from_cell,
    form_action,
    hidden_fields,
    money,
    next_page_url,
    parse_account_page,
    parse_filed_at,
    parse_filed_date,
    parse_transactions,
    replace_transaction_day,
    replace_filer_contributions,
    reported_transaction_types_to_refresh,
    retain_filed_since,
    retry_wait_seconds,
    summary_reconciliation_ids,
    top_contributors_need_refresh,
    transaction_dates_for_sync,
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

    def test_statewide_transactions_include_filer_id(self):
        page = """
        <table><tr>
          <td>5806472</td><td>09/11/2026</td><td>Original</td>
          <td><a href="sooDetail.do?cneCommitteeId=12345">Committee</a></td>
          <td>Jane Doe</td><td>Cash Contribution</td><td>$100.00</td>
        </tr></table>
        """
        self.assertEqual(filer_id_from_cell('x?filerId=12345'), 12345)
        self.assertEqual(parse_transactions(page)[0]["filerID"], 12345)

    def test_transaction_next_page(self):
        page = '''<script>window.location="/orestar/gotoPublicTransactionSearchResults.do?cneSearchButtonName=next&amp;cneSearchPageIdx=1"</script>'''
        self.assertEqual(
            next_page_url(page),
            "https://secure.sos.state.or.us/orestar/gotoPublicTransactionSearchResults.do?cneSearchButtonName=next&cneSearchPageIdx=1",
        )

    def test_filed_date(self):
        page = """
        <table><tr><td>Transaction Sub Type</td><td>:</td><td>Cash</td>
        <td>Filed Date </td><td>:</td><td>09/16/2026 10:37:00 AM</td></tr></table>
        """
        self.assertEqual(parse_filed_date(page), "2026-09-16")
        self.assertEqual(parse_filed_at(page), "2026-09-16T10:37:00")

    def test_top_contributors_are_combined_and_ranked(self):
        transactions = [
            {"name": "Jane Doe", "amount": 100},
            {"name": "  JANE   DOE ", "amount": 75.25},
            {"name": "Acme PAC", "amount": 200},
        ]
        self.assertEqual(
            aggregate_top_contributors(transactions),
            [
                {"name": "Acme PAC", "amount": 200.0},
                {"name": "Jane Doe", "amount": 175.25},
            ],
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

    def test_top_contributors_refresh_only_when_changed_or_missing(self):
        summary = {"contributionsYTD": 150, "expendituresYTD": 80}
        complete = {
            "contributionsYTD": 150,
            "topContributorsSince2026": [{"name": "Jane Doe", "amount": 100}],
        }
        self.assertFalse(top_contributors_need_refresh(summary, complete))

        changed = dict(complete, contributionsYTD=125)
        self.assertTrue(top_contributors_need_refresh(summary, changed))

        missing = {"contributionsYTD": 150}
        self.assertTrue(top_contributors_need_refresh(summary, missing))
        self.assertTrue(top_contributors_need_refresh(summary, dict(complete, financeDetailsPending=True)))

    def test_reported_transactions_refresh_when_totals_change_or_fields_are_missing(self):
        summary = {"contributionsYTD": 150, "expendituresYTD": 80}
        complete = {
            **summary,
            "reportedContributions7Days": [],
            "reportedExpenditures7Days": [],
        }
        self.assertEqual(reported_transaction_types_to_refresh(summary, complete), set())
        self.assertEqual(
            reported_transaction_types_to_refresh(summary, dict(complete, expendituresYTD=70)),
            {"E"},
        )
        missing = dict(complete)
        del missing["reportedContributions7Days"]
        self.assertEqual(reported_transaction_types_to_refresh(summary, missing), {"C"})
        self.assertEqual(
            reported_transaction_types_to_refresh(summary, dict(complete, financeDetailsPending=True)),
            {"C", "E"},
        )

    def test_detail_recovery_is_batched_in_source_order(self):
        candidates = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]
        previous = {
            "a": {"dataError": "Refresh failed: HTTP Error 403: Forbidden"},
            "b": {"financeDetailsPending": True},
            "c": {"dataError": None},
            "d": {"financeDetailsPending": True},
        }
        self.assertEqual(detail_recovery_ids(candidates, previous, limit=2), {"a", "b"})

    def test_expired_reported_transactions_are_removed_from_cache(self):
        transactions = [
            {"id": "1", "filedDate": "2026-09-10"},
            {"id": "2", "filedDate": "2026-09-11"},
            {"id": "3", "filedDate": "2026-09-18"},
        ]
        self.assertEqual(
            [item["id"] for item in retain_filed_since(transactions, date(2026, 9, 11))],
            ["2", "3"],
        )

    def test_collective_sync_dates_cover_full_window_once_then_recent_days(self):
        now = datetime.fromisoformat("2026-09-18T12:00:00-07:00")
        rolling = transaction_dates_for_sync(now, {})
        self.assertEqual((rolling[0], rolling[-1]), (date(2026, 9, 11), date(2026, 9, 18)))
        recent = transaction_dates_for_sync(now, {"rollingReconciledOn": "2026-09-18"})
        self.assertEqual(recent, [date(2026, 9, 17), date(2026, 9, 18)])

    def test_replacing_a_filed_day_removes_deleted_transactions(self):
        cached = {
            "1": {"id": "1", "filerID": 10, "transactionType": "C", "filedDate": "2026-09-18"},
            "2": {"id": "2", "filerID": 20, "transactionType": "E", "filedDate": "2026-09-18"},
        }
        changed = replace_transaction_day(
            cached,
            "C",
            date(2026, 9, 18),
            [{"id": "3", "filerID": 30, "date": "2026-09-17", "name": "New", "category": "Cash", "amount": 5}],
        )
        self.assertEqual(set(cached), {"2", "3"})
        self.assertEqual(changed, {10, 30})
        self.assertEqual(cached["3"]["filedDate"], "2026-09-18")

    def test_unmapped_statewide_row_preserves_matching_cached_transaction(self):
        cached = {
            "1": {"id": "1", "filerID": 10, "transactionType": "C", "filedDate": "2026-09-18"},
            "2": {"id": "2", "filerID": 20, "transactionType": "C", "filedDate": "2026-09-18"},
        }
        changed = replace_transaction_day(
            cached,
            "C",
            date(2026, 9, 18),
            [
                {"id": "1", "date": "2026-09-17", "name": "Unknown", "amount": 10},
                {"id": "3", "filerID": 30, "date": "2026-09-17", "name": "New", "amount": 5},
            ],
        )
        self.assertEqual(set(cached), {"1", "3"})
        self.assertEqual(cached["1"]["filerID"], 10)
        self.assertEqual(changed, {20, 30})

    def test_summary_reconciliation_sorts_missing_timestamps_safely(self):
        candidates = [
            {"id": "missing", "filerID": 10},
            {"id": "dated", "filerID": 20},
        ]
        previous = {
            "missing": {"financeSummaryUpdatedAt": None},
            "dated": {"financeSummaryUpdatedAt": "2026-09-01T00:00:00-07:00"},
        }
        now = datetime.fromisoformat("2026-09-21T09:00:00-07:00")
        self.assertEqual(
            summary_reconciliation_ids(candidates, previous, set(), now),
            {"missing", "dated"},
        )

    def test_history_backfill_retains_older_contribution_reported_this_week(self):
        cached = {
            "old": {"id": "old", "filerID": 10, "transactionType": "C", "date": "2025-12-30", "filedDate": "2026-09-18", "amount": 50},
            "current": {"id": "current", "filerID": 10, "transactionType": "C", "date": "2026-09-17", "filedDate": "2026-09-18", "amount": 100},
            "removed": {"id": "removed", "filerID": 10, "transactionType": "C", "date": "2026-07-01", "filedDate": "2026-07-02", "amount": 20},
        }
        replace_filer_contributions(
            cached, 10, [{"id": "current", "date": "2026-09-17", "name": "Donor", "amount": 100}]
        )
        self.assertEqual(set(cached), {"old", "current"})
        self.assertEqual(cached["current"]["filedDate"], "2026-09-18")
        self.assertEqual(cached["old"]["filedDate"], "2026-09-18")

    def test_candidate_finance_lists_are_derived_from_shared_ledger(self):
        now = datetime.fromisoformat("2026-09-18T12:00:00-07:00")
        candidate = {"id": "jane", "name": "Jane", "filerID": 123}
        previous = {"contributionsYTD": 100, "expendituresYTD": 20, "balanceDeficit": 80}
        transactions = [
            {"id": "1", "filerID": 123, "transactionType": "C", "filedDate": "2026-09-18", "filedAt": "2026-09-18T00:00:00", "date": "2026-09-17", "name": "Donor", "category": "Cash", "amount": 75},
            {"id": "2", "filerID": 123, "transactionType": "C", "filedDate": "2026-08-01", "filedAt": "2026-08-01T00:00:00", "date": "2026-07-31", "name": "Donor", "category": "Cash", "amount": 25},
        ]
        item, failed = candidate_from_collective_data(
            candidate, previous, transactions, True, False, now
        )
        self.assertFalse(failed)
        self.assertEqual([entry["id"] for entry in item["reportedContributions7Days"]], ["1"])
        self.assertEqual(item["topContributorsSince2026"], [{"name": "Donor", "amount": 100.0}])
        self.assertFalse(item["financeDetailsPending"])


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
