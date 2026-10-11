"""
Tests for backend/preprocessing.py  (Member 2)

Run from the backend/ folder with either:
    python -m unittest discover -s tests -v
    python -m pytest tests -v          (if pytest is installed)
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from preprocessing import (  # noqa: E402
    EXCLUDED_COLUMNS, PreprocessingError, get_dataset_preview,
    load_and_preprocess,
)

HEADER = ("accident_id,city,state,latitude,longitude,date,time,hour,day_of_week,"
          "is_weekend,road_type,lanes,traffic_signal,weather,visibility,temperature,"
          "traffic_density,cause,accident_severity,vehicles_involved,casualties,"
          "is_peak_hour,festival,risk_score")

ROW_A = ("0,Pune,Maharashtra,18.68,73.93,2023-10-22,5:00,5,Sunday,1,highway,3,1,"
         "fog,low,32,high,weather,fatal,2,2,0,None,0.85")
ROW_B = ("1,Mumbai,Maharashtra,18.81,72.79,2023-05-21,18:00,18,Monday,0,urban,4,0,"
         "clear,high,20,low,drunk driving,minor,4,3,1,Holi,0.1")

REAL_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "indian_roads_dataset.csv")


class CsvTestCase(unittest.TestCase):
    def write_csv(self, *rows, header=HEADER):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join([header, *rows]) + "\n")
        self.addCleanup(os.remove, path)
        return path


class TestTransactionConversion(CsvTestCase):
    def test_one_transaction_per_retained_record(self):
        tx, stats = load_and_preprocess(self.write_csv(ROW_A, ROW_B))
        self.assertEqual(len(tx), 2)
        self.assertEqual(stats["transaction_count"], 2)
        self.assertEqual(stats["raw_row_count"], 2)

    def test_items_are_sets_of_column_equals_value(self):
        tx, _ = load_and_preprocess(self.write_csv(ROW_A))
        self.assertIsInstance(tx[0], set)
        self.assertIn("weather=fog", tx[0])
        self.assertIn("road_type=highway", tx[0])
        self.assertIn("accident_severity=fatal", tx[0])
        self.assertIn("cause=weather", tx[0])

    def test_derived_attributes(self):
        tx, _ = load_and_preprocess(self.write_csv(ROW_A, ROW_B))
        self.assertIn("time_of_day=night", tx[0])       # hour 5
        self.assertIn("time_of_day=evening", tx[1])     # hour 18
        self.assertIn("season=post_monsoon", tx[0])     # October
        self.assertIn("season=summer", tx[1])           # May
        self.assertIn("temperature=hot", tx[0])         # 32
        self.assertIn("temperature=cool", tx[1])        # 20
        self.assertIn("traffic_signal=yes", tx[0])
        self.assertIn("lanes=3", tx[0])

    def test_multiword_values_have_no_spaces(self):
        tx, _ = load_and_preprocess(self.write_csv(ROW_B.replace("Holi", "New Year")))
        self.assertIn("cause=drunk_driving", tx[0])
        self.assertIn("festival=new_year", tx[0])
        self.assertTrue(all(" " not in item for item in tx[0]))


class TestExclusions(CsvTestCase):
    def test_ids_coordinates_and_leakage_never_become_items(self):
        tx, stats = load_and_preprocess(self.write_csv(ROW_A, ROW_B))
        banned = ("accident_id=", "latitude=", "longitude=", "date=", "time=",
                  "hour=", "state=", "is_weekend=", "visibility=", "is_peak_hour=",
                  "casualties=", "risk_score=")
        for t in tx:
            for item in t:
                self.assertFalse(item.startswith(banned), item)
        for col in EXCLUDED_COLUMNS:
            self.assertIn(col, stats["attributes_excluded"])
            self.assertNotIn(col, stats["attributes_used"])

    def test_user_exclude(self):
        tx, stats = load_and_preprocess(self.write_csv(ROW_A), exclude=["city"])
        self.assertFalse(any(i.startswith("city=") for i in tx[0]))
        self.assertNotIn("city", stats["attributes_used"])

    def test_cannot_exclude_severity_and_unknown_names_rejected(self):
        tx, _ = load_and_preprocess(self.write_csv(ROW_A), exclude=["accident_severity"])
        self.assertIn("accident_severity=fatal", tx[0])
        with self.assertRaises(PreprocessingError):
            load_and_preprocess(self.write_csv(ROW_A), exclude=["nonsense"])


class TestMissingAndMessyValues(CsvTestCase):
    def test_no_festival_none_is_not_an_item(self):
        tx, stats = load_and_preprocess(self.write_csv(ROW_A, ROW_B))
        self.assertFalse(any(i.startswith("festival=") for i in tx[0]))
        self.assertIn("festival=holi", tx[1])
        self.assertEqual(stats["missing_values_per_attribute"]["festival"], 1)

    def test_missing_cell_skips_item_but_keeps_record(self):
        row = ROW_A.replace(",fog,low,", ",,low,")  # blank weather
        tx, stats = load_and_preprocess(self.write_csv(row, ROW_B))
        self.assertEqual(len(tx), 2)
        self.assertFalse(any(i.startswith("weather=") for i in tx[0]))
        self.assertEqual(stats["missing_values_per_attribute"]["weather"], 1)

    def test_junk_tokens_treated_as_missing(self):
        for junk in ("NaN", "NULL", "unknown", "N/A", "?"):
            row = ROW_A.replace(",fog,low,", f",{junk},low,")
            tx, _ = load_and_preprocess(self.write_csv(row, ROW_B))
            self.assertFalse(any(i.startswith("weather=") for i in tx[0]), junk)

    def test_inconsistent_case_and_whitespace_are_normalised(self):
        row = ROW_A.replace(",highway,", ", HighWay ,").replace(",fog,", ",  FOG,")
        tx, _ = load_and_preprocess(self.write_csv(row, ROW_B))
        self.assertIn("road_type=highway", tx[0])
        self.assertIn("weather=fog", tx[0])

    def test_unparsable_numbers_and_dates_do_not_crash(self):
        row = ROW_A.replace(",5,Sunday,", ",abc,Sunday,").replace("2023-10-22", "not-a-date").replace(",32,high,", ",hot!,high,")
        tx, stats = load_and_preprocess(self.write_csv(row, ROW_B))
        self.assertEqual(len(tx), 2)
        self.assertFalse(any(i.startswith(("time_of_day=", "season=", "temperature=")) for i in tx[0]))

    def test_out_of_range_hour_is_ignored(self):
        row = ROW_A.replace(",5,Sunday,", ",99,Sunday,")
        tx, _ = load_and_preprocess(self.write_csv(row, ROW_B))
        self.assertFalse(any(i.startswith("time_of_day=") for i in tx[0]))

    def test_record_without_severity_is_dropped_and_counted(self):
        row = ROW_A.replace(",fatal,", ",,")
        tx, stats = load_and_preprocess(self.write_csv(row, ROW_B))
        self.assertEqual(len(tx), 1)
        self.assertEqual(stats["dropped_rows"]["missing_severity"], 1)
        self.assertEqual(stats["raw_row_count"], 2)

    def test_duplicates_ignoring_id_are_dropped(self):
        dup = "7" + ROW_A[1:]
        tx, stats = load_and_preprocess(self.write_csv(ROW_A, dup, ROW_B))
        self.assertEqual(len(tx), 2)
        self.assertEqual(stats["dropped_rows"]["duplicates"], 1)

    def test_blank_lines_and_ragged_header_case(self):
        header = HEADER.upper().replace("ACCIDENT_ID", " Accident_ID ")
        tx, _ = load_and_preprocess(self.write_csv(ROW_A, header=header))
        self.assertEqual(len(tx), 1)


class TestValidation(CsvTestCase):
    def test_missing_file(self):
        with self.assertRaises(PreprocessingError):
            load_and_preprocess("/no/such/file.csv")

    def test_empty_file(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        self.addCleanup(os.remove, path)
        with self.assertRaises(PreprocessingError):
            load_and_preprocess(path)

    def test_header_only(self):
        with self.assertRaises(PreprocessingError):
            load_and_preprocess(self.write_csv())

    def test_missing_required_column(self):
        header = HEADER.replace("weather,", "")
        with self.assertRaises(PreprocessingError) as ctx:
            load_and_preprocess(self.write_csv(ROW_A, header=header))
        self.assertIn("weather", str(ctx.exception))

    def test_error_is_a_value_error_for_flask_handlers(self):
        self.assertTrue(issubclass(PreprocessingError, ValueError))


class TestStats(CsvTestCase):
    def test_stats_are_json_serialisable_and_consistent(self):
        tx, stats = load_and_preprocess(self.write_csv(ROW_A, ROW_B))
        json.dumps(stats)  # must not raise (no numpy ints, no pd.NA)
        counts = {d["item"]: d["count"] for d in stats["item_frequencies"]}
        for item, c in counts.items():
            self.assertEqual(c, sum(item in t for t in tx))
        self.assertEqual(stats["distinct_item_count"], len(counts))
        self.assertAlmostEqual(stats["avg_items_per_transaction"],
                               sum(map(len, tx)) / len(tx), places=2)
        self.assertEqual(sorted(stats["attribute_values"]["weather"]), ["clear", "fog"])

    def test_preview(self):
        prev = get_dataset_preview(self.write_csv(ROW_A, ROW_B), n=1)
        self.assertEqual(prev["row_count"], 2)
        self.assertEqual(len(prev["rows"]), 1)
        self.assertEqual(prev["rows"][0]["city"], "Pune")
        json.dumps(prev)


@unittest.skipUnless(os.path.isfile(REAL_CSV), "real dataset not in backend/data/")
class TestRealDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tx, cls.stats = load_and_preprocess(REAL_CSV)

    def test_every_row_retained(self):
        self.assertEqual(self.stats["raw_row_count"], len(self.tx))
        self.assertEqual(sum(self.stats["dropped_rows"].values()), 0)

    def test_counts_match_manual_pandas_count(self):
        import pandas as pd
        df = pd.read_csv(REAL_CSV, keep_default_na=False)
        manual = int(((df.weather == "rain") & (df.road_type == "highway")).sum())
        both = sum({"weather=rain", "road_type=highway"} <= t for t in self.tx)
        self.assertEqual(manual, both)
        self.assertEqual(int((df.accident_severity == "fatal").sum()),
                         sum("accident_severity=fatal" in t for t in self.tx))

    def test_each_transaction_has_exactly_one_severity(self):
        for t in self.tx:
            self.assertEqual(sum(i.startswith("accident_severity=") for i in t), 1)

    def test_item_vocabulary_is_small_and_clean(self):
        self.assertLess(self.stats["distinct_item_count"], 100)
        self.assertFalse(any(i.split("=")[0] in ("accident_id", "latitude", "longitude")
                             for t in self.tx for i in t))


if __name__ == "__main__":
    unittest.main()