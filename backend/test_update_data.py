import unittest

from backend.update_data import money, parse_account_page


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


if __name__ == "__main__":
    unittest.main()
