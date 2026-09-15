from datetime import datetime, timedelta
import unittest

from backend.update_data import (
    add_ten_day_deltas,
    form_action,
    hidden_fields,
    money,
    parse_account_page,
    parse_transactions,
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


if __name__ == "__main__":
    unittest.main()
