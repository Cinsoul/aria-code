"""Every task in the eval bank can be solved, and its trap is caught.

`--check` proves each task starts red. That does not prove the grader can be
satisfied, or that it fails the tempting half-fix the task is built around —
a grader with either flaw measures nothing while looking rigorous. For each
task here this writes a correct solution into a copy of the fixture and
requires a pass, then writes the half-fix and requires the named test to fail.

(test_operations_suite.py does the same for the first operations tasks.)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures"
SUITES = ROOT / "evals" / "suites"


class _Task(unittest.TestCase):
    fixture = ""

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp()) / self.fixture
        shutil.copytree(FIXTURES / self.fixture, self.dir)
        self.addCleanup(shutil.rmtree, self.dir.parent, True)

    def write(self, name: str, source: str) -> None:
        (self.dir / name).write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")

    def write_json(self, name: str, data) -> None:
        (self.dir / name).write_text(json.dumps(data), encoding="utf-8")

    def grade(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                              cwd=self.dir, capture_output=True, text=True, timeout=120)

    def assertPasses(self) -> None:
        proc = self.grade()
        self.assertEqual(proc.returncode, 0, proc.stdout[-1500:])

    def assertFailsOn(self, test_name: str) -> None:
        proc = self.grade()
        self.assertNotEqual(proc.returncode, 0, "the grader accepted the mistake it exists to catch")
        self.assertIn(test_name, proc.stdout)


# --- software -------------------------------------------------------------


class CsvQuotedFields(_Task):
    fixture = "csv_quoted_fields"

    def test_the_csv_module_passes(self) -> None:
        self.write("orders.py", """
            import csv
            import io


            def parse_line(line):
                return next(csv.reader([line]))


            def load_orders(text):
                rows = [row for row in csv.reader(io.StringIO(text)) if row]
                header, out = rows[0], []
                for row in rows[1:]:
                    if len(row) != len(header):
                        raise ValueError(f"expected {len(header)} fields, got {len(row)}")
                    out.append(dict(zip(header, row)))
                return out
            """)
        self.assertPasses()

    def test_line_by_line_parsing_fails_on_a_multiline_note(self) -> None:
        self.write("orders.py", """
            import csv


            def parse_line(line):
                return next(csv.reader([line]))


            def load_orders(text):
                lines = [line for line in text.splitlines() if line.strip()]
                header = parse_line(lines[0])
                out = []
                for line in lines[1:]:
                    row = parse_line(line)
                    if len(row) != len(header):
                        raise ValueError("bad row")
                    out.append(dict(zip(header, row)))
                return out
            """)
        self.assertFailsOn("test_a_note_can_span_lines")


class SharedDefaultState(_Task):
    fixture = "shared_default_state"

    def _shipment(self, parcels: str, tags: str) -> None:
        self.write("shipment.py", f"""
            class Shipment:
                def __init__(self, shipment_id, parcels=None, tags=None):
                    self.shipment_id = shipment_id
                    self.parcels = {parcels}
                    self.tags = {tags}

                def add(self, parcel_id):
                    self.parcels.append(parcel_id)

                def tag(self, key, value):
                    self.tags[key] = value
            """)

    def test_copying_what_was_passed_passes(self) -> None:
        self._shipment("list(parcels or [])", "dict(tags or {})")
        self.assertPasses()

    def test_none_defaults_alone_still_alias_the_callers_list(self) -> None:
        self._shipment("parcels if parcels is not None else []", "tags if tags is not None else {}")
        self.assertFailsOn("test_the_callers_list_is_left_alone")


class RetryTransientOnly(_Task):
    fixture = "retry_transient_only"

    def _fetch(self, catch: str) -> None:
        self.write("fetch.py", f"""
            import time

            TRANSIENT = (ConnectionError, TimeoutError)


            def with_retries(call, attempts=3, delay=0.5, sleep=time.sleep):
                if attempts < 1:
                    raise ValueError("attempts must be at least 1")
                for i in range(attempts):
                    try:
                        return call()
                    except {catch}:
                        if i == attempts - 1:
                            raise
                        sleep(delay * 2 ** i)
            """)

    def test_retrying_transient_errors_only_passes(self) -> None:
        self._fetch("TRANSIENT")
        self.assertPasses()

    def test_retrying_everything_fails(self) -> None:
        self._fetch("Exception")
        self.assertFailsOn("test_a_bad_request_is_not_retried")


# --- finance ----------------------------------------------------------------


_ALLOCATE = """
    def allocate(total_cents, weights):
        if any(w < 0 for w in weights) or not any(weights):
            raise ValueError("weights must be non-negative and not all zero")
        whole = sum(weights)
        sign = -1 if total_cents < 0 else 1
        amount = abs(total_cents)
        parts = [divmod(amount * w, whole) for w in weights]
        shares = [q for q, _r in parts]
        order = sorted(range(len(weights)), key=lambda i: (-parts[i][1], i))
        for i in order[: amount - sum(shares)]:
            shares[i] += 1
        return [sign * s for s in shares]
    """


class AllocateCents(_Task):
    fixture = "allocate_cents"

    def test_largest_remainder_passes(self) -> None:
        self.write("allocate.py", _ALLOCATE)
        self.assertPasses()

    def test_flooring_a_refund_fails(self) -> None:
        # Largest remainder on the signed total: floor division pushes every
        # negative share down, and the "leftover" is negative.
        self.write("allocate.py", _ALLOCATE.replace(
            "sign = -1 if total_cents < 0 else 1\n        amount = abs(total_cents)",
            "sign = 1\n        amount = total_cents"))
        self.assertFailsOn("test_a_refund_mirrors_a_charge")


class DrawdownRunningPeak(_Task):
    fixture = "drawdown_running_peak"

    def _perf(self, periods: str) -> None:
        self.write("perf.py", f"""
            def max_drawdown(values):
                if not values:
                    raise ValueError("no values")
                peak, worst = values[0], 0.0
                for v in values:
                    peak = max(peak, v)
                    worst = max(worst, (peak - v) / peak)
                return worst


            def annualized_return(closes, periods_per_year=252):
                if len(closes) < 2:
                    raise ValueError("need at least two closes")
                return (closes[-1] / closes[0]) ** (periods_per_year / ({periods})) - 1
            """)

    def test_running_peak_and_return_count_passes(self) -> None:
        self._perf("len(closes) - 1")
        self.assertPasses()

    def test_counting_closes_instead_of_returns_fails(self) -> None:
        self._perf("len(closes)")
        self.assertFailsOn("test_one_year_of_closes")


class FifoCostBasis(_Task):
    fixture = "fifo_cost_basis"

    def _lots(self, order: str) -> None:
        self.write("lots.py", f"""
            import csv
            from collections import defaultdict, deque
            from pathlib import Path


            def load(name="trades.csv"):
                with open(Path(__file__).parent / name, newline="", encoding="utf-8") as fh:
                    return list(csv.DictReader(fh))


            def realized_gains(trades=None):
                trades = trades if trades is not None else load()
                lots, gains = defaultdict(deque), defaultdict(float)
                for t in {order}:
                    sym, q, price = t["symbol"], float(t["qty"]), float(t["price"])
                    if t["side"] == "buy":
                        lots[sym].append([q, price])
                        continue
                    if q > sum(lot[0] for lot in lots[sym]) + 1e-9:
                        raise ValueError(f"selling more {{sym}} than is held")
                    while q > 1e-9:
                        lot = lots[sym][0]
                        used = min(q, lot[0])
                        gains[sym] += used * (price - lot[1])
                        lot[0] -= used
                        q -= used
                        if lot[0] <= 1e-9:
                            lots[sym].popleft()
                return {{sym: round(g, 2) for sym, g in gains.items()}}
            """)

    def test_fifo_in_date_order_passes(self) -> None:
        self._lots('sorted(trades, key=lambda t: t["date"])')
        self.assertPasses()

    def test_fifo_in_file_order_fails(self) -> None:
        self._lots("trades")
        self.assertFailsOn("test_trades_are_matched_in_date_order")


class ArAging(_Task):
    fixture = "ar_aging"

    def _aging(self, *, apply_late_payments: bool) -> None:
        import csv
        from collections import defaultdict
        from datetime import date

        as_of = date(2026, 9, 30)
        paid: dict[str, float] = defaultdict(float)
        for p in csv.DictReader((self.dir / "payments.csv").open()):
            if apply_late_payments or date.fromisoformat(p["received_date"]) <= as_of:
                paid[p["invoice_no"]] += float(p["amount"])
        out: dict[str, dict[str, float]] = {}
        for inv in csv.DictReader((self.dir / "invoices.csv").open()):
            if date.fromisoformat(inv["issue_date"]) > as_of:
                continue
            owed = float(inv["amount"]) - paid[inv["invoice_no"]]
            days = (as_of - date.fromisoformat(inv["due_date"])).days
            bucket = ("current" if days <= 0 else "1-30" if days <= 30 else "31-60" if days <= 60
                      else "61-90" if days <= 90 else "90+")
            row = out.setdefault(inv["customer"], dict.fromkeys(("current", "1-30", "31-60", "61-90", "90+"), 0.0))
            row[bucket] += max(owed, 0.0)
        self.write_json("aging.json", out)

    def test_books_as_of_month_end_pass(self) -> None:
        self._aging(apply_late_payments=False)
        self.assertPasses()

    def test_applying_an_october_payment_fails(self) -> None:
        self._aging(apply_late_payments=True)
        self.assertFailsOn("test_a_payment_after_month_end_is_not_applied")


class SplitAdjustedReturns(_Task):
    fixture = "split_adjusted_returns"

    def test_adjusted_returns_pass(self) -> None:
        self.write_json("returns.json", {"NOVA": 118 / (400 / 4) - 1, "ORBT": 33.48 / (3.10 * 10) - 1,
                                         "PIKE": 55.12 / 52 - 1})
        self.assertPasses()

    def test_percent_is_accepted(self) -> None:
        self.write_json("returns.json", {"NOVA": 18.0, "ORBT": 8.0, "PIKE": 6.0})
        self.assertPasses()

    def test_raw_closes_fail(self) -> None:
        self.write_json("returns.json", {"NOVA": 118 / 400 - 1, "ORBT": 33.48 / 3.10 - 1,
                                         "PIKE": 55.12 / 52 - 1})
        self.assertFailsOn("test_a_forward_split_is_not_a_crash")


# --- logistics --------------------------------------------------------------


class DimWeightBilling(_Task):
    fixture = "dim_weight_billing"

    def _rating(self, rounding: str) -> None:
        self.write("rating.py", f"""
            import math

            DIM_DIVISOR = 5000
            RATES = {{"A": (8.00, 2.50), "B": (12.00, 3.50)}}


            def chargeable_weight(actual_kg, length_cm, width_cm, height_cm):
                if actual_kg < 0 or min(length_cm, width_cm, height_cm) <= 0:
                    raise ValueError("weight and dimensions must be positive")
                volumetric = length_cm * width_cm * height_cm / DIM_DIVISOR
                return max(0.5, {rounding}(max(actual_kg, volumetric) * 2) / 2)


            def quote(actual_kg, dims, zone):
                if zone not in RATES:
                    raise ValueError(f"unknown zone {{zone!r}}")
                weight = chargeable_weight(actual_kg, *dims)
                first, extra = RATES[zone]
                return round(first + round((weight - 0.5) / 0.5) * extra, 2)
            """)

    def test_rounding_up_passes(self) -> None:
        self._rating("math.ceil")
        self.assertPasses()

    def test_rounding_to_nearest_fails(self) -> None:
        self._rating("round")
        self.assertFailsOn("test_actual_weight_rounds_up")


class EtaBusinessDays(_Task):
    fixture = "eta_business_days"

    def _eta(self, cutoff: str) -> None:
        self.write("eta.py", f"""
            import csv
            from datetime import timedelta
            from pathlib import Path

            CUTOFF_HOUR = 15

            with open(Path(__file__).with_name("holidays.csv"), newline="", encoding="utf-8") as fh:
                HOLIDAYS = {{row["date"] for row in csv.DictReader(fh)}}


            def _working(day):
                return day.weekday() < 5 and day.isoformat() not in HOLIDAYS


            def _next_working(day):
                day += timedelta(days=1)
                while not _working(day):
                    day += timedelta(days=1)
                return day


            def estimated_delivery(order_time, transit_days):
                day = order_time.date()
                if not (_working(day) and {cutoff}):
                    day = _next_working(day)
                for _ in range(transit_days):
                    day = _next_working(day)
                return day
            """)

    def test_working_days_and_cutoff_pass(self) -> None:
        self._eta("order_time.hour < CUTOFF_HOUR")
        self.assertPasses()

    def test_counting_15_00_as_before_cutoff_fails(self) -> None:
        self._eta("order_time.hour <= CUTOFF_HOUR and order_time.minute == 0")
        self.assertFailsOn("test_the_cutoff_itself_is_too_late")


class SlaTimezones(_Task):
    fixture = "sla_timezones"

    def _sla(self, parse: str) -> None:
        self.write("sla.py", f"""
            from datetime import datetime


            def _parse(stamp):
                {parse}


            def hours_late(promised, delivered):
                late = (_parse(delivered) - _parse(promised)).total_seconds() / 3600
                return max(0.0, round(late, 2))


            def late_shipments(rows, grace_minutes=30):
                return [r["id"] for r in rows
                        if hours_late(r["promised"], r["delivered"]) * 60 > grace_minutes]
            """)

    def test_aware_timestamps_pass(self) -> None:
        self._sla("parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))\n"
                  "                if parsed.tzinfo is None:\n"
                  "                    raise ValueError(f'no UTC offset in {stamp!r}')\n"
                  "                return parsed")
        self.assertPasses()

    def test_assuming_utc_for_a_naive_stamp_fails(self) -> None:
        self._sla("from datetime import timezone\n"
                  "                parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))\n"
                  "                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)")
        self.assertFailsOn("test_a_timestamp_without_an_offset_is_refused")


class CarrierOnTime(_Task):
    fixture = "carrier_on_time"

    def _kpi(self, *, dedupe: bool, overdue_in_transit_late: bool) -> None:
        import csv
        from datetime import date

        rows = list(csv.DictReader((self.dir / "deliveries.csv").open()))
        if dedupe:
            rows = list({r["shipment_id"]: r for r in rows}.values())
        counts: dict[str, list[int]] = {}
        for r in rows:
            promised = date.fromisoformat(r["promised_date"])
            if r["status"] == "cancelled":
                continue
            if r["status"] == "in_transit":
                if overdue_in_transit_late and promised < date(2026, 9, 30):
                    counts.setdefault(r["carrier"], [0, 0])[0] += 1
                continue
            c = counts.setdefault(r["carrier"], [0, 0])
            c[0] += 1
            c[1] += date.fromisoformat(r["delivered_date"]) <= promised
        self.write_json("kpi.json", {k: {"shipments": n, "on_time_rate": ok / n}
                                     for k, (n, ok) in counts.items()})

    def test_counting_each_shipment_once_passes(self) -> None:
        self._kpi(dedupe=True, overdue_in_transit_late=True)
        self.assertPasses()

    def test_counting_every_scan_fails(self) -> None:
        self._kpi(dedupe=False, overdue_in_transit_late=True)
        self.assertFailsOn("test_shipments_counted_once_cancellations_excluded")

    def test_leaving_out_an_overdue_parcel_fails(self) -> None:
        self._kpi(dedupe=True, overdue_in_transit_late=False)
        self.assertFailsOn("test_an_overdue_parcel_in_transit_is_late")


# --- the suite files --------------------------------------------------------


class TheBank(unittest.TestCase):
    def _tasks(self):
        tasks = []
        for suite in sorted(SUITES.glob("*.yaml")):
            tasks += yaml.safe_load(suite.read_text(encoding="utf-8"))["tasks"]
        return tasks

    def test_every_fixture_is_run_by_a_suite(self) -> None:
        on_disk = {p.name for p in FIXTURES.iterdir() if p.is_dir()}
        used = {t["fixture"] for t in self._tasks()}
        self.assertEqual(on_disk - used, set(), "fixture with no task — it is never measured")
        self.assertEqual(used - on_disk, set())

    def test_ids_are_unique(self) -> None:
        ids = [t["id"] for t in self._tasks()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_data_files_are_protected(self) -> None:
        for task in self._tasks():
            fixture = FIXTURES / task["fixture"]
            if any(fixture.glob("*.csv")):
                with self.subTest(task=task["id"]):
                    self.assertIn("*.csv", task.get("protect", []),
                                  "an agent could edit the data until it passes")

    def test_the_bank_covers_all_three_areas(self) -> None:
        tags = [set(t["tags"]) for t in self._tasks()]
        self.assertGreaterEqual(sum("software" in t for t in tags), 6)
        self.assertGreaterEqual(sum("finance" in t or "payments" in t for t in tags), 6)
        self.assertGreaterEqual(sum("logistics" in t for t in tags), 6)


if __name__ == "__main__":
    unittest.main()
