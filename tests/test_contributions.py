import subprocess
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from unittest.mock import patch

from scripts import update_contributions as counter


class ContributionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
        self.metadata = {
            "createdAt": "2025-01-05T08:01:50Z",
            "contributionsCollection": {"contributionYears": [2026, 2025]},
        }

    def collect(self, totals, metadata=None, now=None):
        data = {
            f"y{year}": {"contributionCalendar": {"totalContributions": total}}
            for year, total in totals.items()
        }
        with patch.object(
            counter, "graphql", side_effect=[metadata or self.metadata, data]
        ) as request:
            result = counter.collect_contributions(now or self.now)
        return result, request.call_args.args[0]

    def test_all_years_including_zero_and_pre_account_contributions(self):
        self.metadata["contributionsCollection"]["contributionYears"] = [2026, 2024]
        totals, query = self.collect({2024: 10, 2025: 0, 2026: 42})
        self.assertEqual(totals, {2024: 10, 2025: 0, 2026: 42})
        self.assertIn('from: "2024-01-01T00:00:00+00:00"', query)
        self.assertIn('to: "2025-12-31T23:59:59+00:00"', query)
        self.assertIn('to: "2026-11-04T12:00:00+00:00"', query)

    def test_new_year_and_leap_year_boundaries(self):
        self.metadata["createdAt"] = "2024-02-29T00:00:00Z"
        now = datetime(2027, 1, 1, tzinfo=timezone.utc)
        totals, query = self.collect({2024: 1, 2025: 2, 2026: 3, 2027: 0}, now=now)
        self.assertEqual(sum(totals.values()), 6)
        self.assertIn('to: "2024-12-31T23:59:59+00:00"', query)
        self.assertIn('to: "2027-01-01T00:00:00+00:00"', query)

    def test_missing_or_invalid_totals_fail_instead_of_undercounting(self):
        with self.assertRaises(KeyError):
            self.collect({2026: 42})
        for value in (None, -1, "42", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.collect({2025: 0, 2026: value})

    def test_invalid_years_fail(self):
        for years in (None, [2027], ["2025"], [True]):
            self.metadata["contributionsCollection"]["contributionYears"] = years
            with self.subTest(years=years), self.assertRaises(ValueError):
                self.collect({})

    def test_graphql_errors_and_missing_user_fail(self):
        for response in (
            '{"errors": [{"message": "Denied"}], "data": {"user": {}}}',
            '{"data": {"user": null}}',
        ):
            with patch.object(
                counter.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, stdout=response),
            ), self.assertRaises(RuntimeError):
                counter.graphql("query")

    def test_fetch_failure_preserves_existing_asset(self):
        with patch.object(
            counter, "collect_contributions", side_effect=RuntimeError("API failure")
        ), patch.object(counter, "OUTPUT") as output:
            with self.assertRaises(RuntimeError):
                counter.main()
            output.write_text.assert_not_called()

    def test_svg_contains_exact_sum_years_and_timestamp(self):
        svg = counter.render_svg({2024: 0, 2025: 108, 2026: 1000}, self.now)
        root = ET.fromstring(svg)
        text = " ".join(root.itertext())
        self.assertIn("1,108", text)
        self.assertIn("2024 (full calendar year)", text)
        self.assertIn("2026 (year to date)", text)
        self.assertIn("2026-11-04 12:00:00 UTC", text)
        self.assertIn("API-visible contributions only", text)
        self.assertIn("Updated daily, not live", text)


if __name__ == "__main__":
    unittest.main()
