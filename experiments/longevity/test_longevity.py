"""Synthetic tests only. No released benchmark rows, model downloads or paid APIs."""
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import longevity as lb


def fixture(index=6, label="A", suffix="one", config="mini"):
    spec = lb.catalog()["tasks"][index]
    return {**{k: spec[k] for k in ("pool", "domain", "format", "metric", "units")},
            "lb_id": spec["mini_id" if config == "mini" else "id"],
            "messages": [{"role": "system", "content": "Synthetic test; not medical data."},
                         {"role": "user", "content": f"Synthetic case {suffix}. Choose A or B."},
                         {"role": "assistant", "content": label}],
            "metadata": "SECRET_REFERENCE_AND_FUTURE_DATA", "task": "SECRET_TASK_METADATA"}


def prepared(*rows):
    raw = b"\n".join(lb.encode(r) for r in rows)
    return lb.prepare(raw, lb.digest(raw), "mini", synthetic=True)


def run_for(bundle, states):
    return {"schema": lb.SCHEMA, "requests_sha256": lb.digest(lb.encode(bundle)),
            "predictions": [{"id": r["id"], "status": status, "answer": value}
                            for r, (status, value) in zip(bundle["requests"], states)]}


class AdapterTests(unittest.TestCase):
    def test_catalog(self):
        tasks = lb.catalog()["tasks"]
        self.assertEqual(len(tasks), 17)
        self.assertEqual(sum(t["n"] for t in tasks), 25457)
        self.assertEqual(sum(t["mini_n"] for t in tasks), 728)
        self.assertEqual(len({t["domain"] for t in tasks}), 5)

    def test_all_task_formats_and_aliases(self):
        for config in ("mini", "benchmark"):
            for i, spec in enumerate(lb.catalog()["tasks"]):
                row = fixture(i, "42" if spec["metric"] == "mae" else "A", config=config)
                raw = lb.encode(row)
                requests, gold = lb.prepare(raw, lb.digest(raw), config, synthetic=True)
                self.assertEqual(gold["labels"][0]["pool"], spec["pool"])
                self.assertNotIn("assistant", str(requests))

    def test_blinding_and_gold_independent_identity(self):
        row = fixture()
        a, gold = prepared(row)
        row["messages"][-1]["content"] = "B"
        row["metadata"] = "ALTERED_FUTURE_DATA"
        b, _ = prepared(row)
        self.assertEqual(a["requests"], b["requests"])
        self.assertNotIn("SECRET", str(a))
        self.assertEqual(gold["labels"][0]["expected"], "A")
        lb.validate_requests(a)

    def test_empty_dataset(self):
        with self.assertRaisesRegex(lb.Rejected, "EMPTY_DATASET"):
            lb.prepare(b"", lb.digest(b""), "mini", synthetic=True)

    def test_hash_required(self):
        with self.assertRaisesRegex(lb.Rejected, "ARTIFACT_DIGEST_MISMATCH"):
            lb.prepare(lb.encode(fixture()), "0" * 64, "mini", synthetic=True)

    def test_rights_review_required(self):
        raw = lb.encode(fixture())
        with self.assertRaisesRegex(lb.Rejected, "RIGHTS_REVIEW_REQUIRED"):
            lb.prepare(raw, lb.digest(raw), "mini")

    def test_duplicate_prompt(self):
        with self.assertRaisesRegex(lb.Rejected, "DUPLICATE_PROMPT"):
            prepared(fixture(), fixture())

    def test_chat_role_and_extra_field_rejected(self):
        for field in ("role", "tool_calls"):
            row = fixture()
            row["messages"][0][field] = "assistant"
            with self.assertRaises(lb.Rejected):
                prepared(row)

    def test_schema_drift(self):
        for key in ("domain", "metric", "pool", "units", "lb_id"):
            row = fixture()
            row[key] = "unexpected"
            with self.assertRaises(lb.Rejected):
                prepared(row)

    def test_extra_configuration_rejected(self):
        raw = lb.encode(fixture())
        with self.assertRaisesRegex(lb.Rejected, "UNSUPPORTED_CONFIG"):
            lb.prepare(raw, lb.digest(raw), "extra", synthetic=True)

    def test_strict_numeric_parser(self):
        for text in ("NaN", "inf", "1e999", "50 or 60", "Age: 50", "50 years", "1e12"):
            with self.assertRaises(lb.Rejected):
                lb.answer(text, "mae")
        self.assertEqual(lb.answer("trace</think>-2.5e1", "mae"), -25)

    def test_ambiguous_classification(self):
        for text in ("A or B", "The answer is A", "", "<think>A", "a"):
            with self.assertRaises(lb.Rejected):
                lb.answer(text, "accuracy")

    def test_strict_json(self):
        for value in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}', 'not-json'):
            with self.assertRaises(lb.Rejected):
                lb.decode(value)

    def test_private_bundle_rejected(self):
        bundle, _ = prepared(fixture())
        bundle["data_class"] = "patient"
        with self.assertRaisesRegex(lb.Rejected, "PRIVATE_DATA_FORBIDDEN"):
            lb.validate_requests(bundle)

    def test_mutated_prompt_rejected(self):
        bundle, _ = prepared(fixture())
        bundle["requests"][0]["messages"][1]["content"] = "changed"
        with self.assertRaisesRegex(lb.Rejected, "PROMPT_DIGEST_MISMATCH"):
            lb.validate_requests(bundle)

    def test_hash_json_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "value.json"
            path.write_text('{"z": 2, "a": 1}\n')
            result = subprocess.run([sys.executable, str(Path(lb.__file__)), "hash-json", str(path)],
                                    check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), lb.digest(lb.encode({"a": 1, "z": 2})))

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            lb.write_new(path, {"first": True})
            with self.assertRaises(FileExistsError):
                lb.write_new(path, {"second": True})
            self.assertEqual(lb.decode(path.read_bytes()), {"first": True})


class ScoringTests(unittest.TestCase):
    def scored(self, gold, run):
        return lb.score(gold, run, lb.digest(lb.encode(gold)))

    def test_classification_denominator_includes_all_nonanswers(self):
        bundle, gold = prepared(*(fixture(label="A" if i < 3 else "B", suffix=str(i)) for i in range(6)))
        run = run_for(bundle, [("answered", "A"), ("abstained", None), ("failed", None),
                               ("answered", "B"), ("answered", "maybe")])
        report = self.scored(gold, run)
        task = next(iter(report["tasks"].values()))
        self.assertEqual(task["accuracy"], 2 / 6)
        self.assertEqual(task["balanced_accuracy"], 1 / 3)
        self.assertEqual(task["coverage"], 2 / 6)
        self.assertEqual(task["counts"], {"answered": 2, "abstained": 1, "failed": 1, "invalid": 1, "missing": 1})
        self.assertFalse(report["official_reproduction"])
        self.assertFalse(report["complete_task_counts"])

    def test_partial_regression_cannot_claim_full_mae(self):
        bundle, gold = prepared(fixture(7, "40"), fixture(7, "60", "two"))
        task = next(iter(self.scored(gold, run_for(bundle, [("answered", "42")]))["tasks"].values()))
        self.assertIsNone(task["mae"])
        self.assertEqual(task["selective_mae"], 2)

    def test_complete_regression(self):
        bundle, gold = prepared(fixture(7, "40"), fixture(7, "60", "two"))
        task = next(iter(self.scored(gold, run_for(bundle, [("answered", "42"), ("answered", "56")]))["tasks"].values()))
        self.assertEqual(task["mae"], 3)

    def test_same_case_comparison(self):
        bundle, gold = prepared(fixture())
        result = lb.compare(gold, run_for(bundle, [("answered", "B")]),
                            run_for(bundle, [("answered", "A")]), lb.digest(lb.encode(gold)))
        self.assertEqual(next(iter(result["tasks"].values()))["improvement"], 1)
        self.assertFalse(result["superiority_established"])

    def test_comparison_refuses_selective_winner(self):
        bundle, gold = prepared(fixture())
        result = lb.compare(gold, run_for(bundle, [("abstained", None)]),
                            run_for(bundle, [("answered", "A")]), lb.digest(lb.encode(gold)))
        self.assertIsNone(next(iter(result["tasks"].values()))["improvement"])

    def test_gold_tamper(self):
        bundle, gold = prepared(fixture())
        frozen = lb.digest(lb.encode(gold))
        gold["labels"][0]["expected"] = "B"
        with self.assertRaisesRegex(lb.Rejected, "GOLD_DIGEST_MISMATCH"):
            lb.score(gold, run_for(bundle, []), frozen)

    def test_wrong_dataset(self):
        bundle, gold = prepared(fixture())
        run = run_for(bundle, [])
        run["requests_sha256"] = "0" * 64
        with self.assertRaisesRegex(lb.Rejected, "RUN_DATASET_MISMATCH"):
            self.scored(gold, run)

    def test_duplicate_unknown_and_bad_status(self):
        bundle, gold = prepared(fixture())
        for mutation in ("duplicate", "unknown", "status", "hidden_answer"):
            run = run_for(bundle, [("answered", "A")])
            if mutation == "duplicate":
                run["predictions"] *= 2
            elif mutation == "unknown":
                run["predictions"][0]["id"] = "unknown"
            else:
                run["predictions"][0]["status"] = "completed" if mutation == "status" else "abstained"
            with self.assertRaises(lb.Rejected):
                self.scored(gold, run)

    def test_all_abstain_has_no_selective_accuracy(self):
        bundle, gold = prepared(fixture())
        task = next(iter(self.scored(gold, run_for(bundle, [("abstained", None)]))["tasks"].values()))
        self.assertIsNone(task["selective_accuracy"])
        self.assertEqual(task["accuracy"], 0)


class PermitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        subprocess.run(["/usr/bin/openssl", "genpkey", "-algorithm", "ED25519", "-out", str(cls.root / "private")],
                       check=True, capture_output=True)
        subprocess.run(["/usr/bin/openssl", "pkey", "-in", str(cls.root / "private"), "-pubout",
                        "-out", str(cls.root / "public")], check=True, capture_output=True)
        cls.key = (cls.root / "public").read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def signed(self, bundle, **changes):
        now = datetime.now(timezone.utc)
        permit = {"schema": "openbody.longevity.permit.v1", "purpose": "public-benchmark-inference",
                  "requests_sha256": lb.digest(lb.encode(bundle)), "data_class": "synthetic",
                  "rights_review": "TEST_ONLY", "provenance_review": "TEST_ONLY", "reviewer": "TEST_KEY",
                  "model": "synthetic-model", "model_revision": "a" * 40,
                  "serving_manifest_sha256": "b" * 64, "max_cases": 100,
                  "not_before": (now - timedelta(minutes=1)).isoformat(),
                  "expires_at": (now + timedelta(minutes=5)).isoformat(),
                  "endpoint": "http://127.0.0.1:12345/v1/chat/completions", **changes}
        raw = lb.encode(permit)
        (self.root / "permit").write_bytes(raw)
        subprocess.run(["/usr/bin/openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(self.root / "private"),
                        "-in", str(self.root / "permit"), "-out", str(self.root / "signature")],
                       check=True, capture_output=True)
        return raw, (self.root / "signature").read_bytes()

    def test_valid_signature(self):
        bundle, _ = prepared(fixture())
        raw, sig = self.signed(bundle)
        self.assertEqual(lb.verify_permit(raw, sig, self.key, lb.digest(self.key),
                                          lb.digest(lb.encode(bundle)))["model"], "synthetic-model")

    def test_signature_and_root_tamper(self):
        bundle, _ = prepared(fixture())
        raw, sig = self.signed(bundle)
        for r, s, pin in ((raw + b" ", sig, lb.digest(self.key)), (raw, b"x" * 64, lb.digest(self.key)),
                          (raw, sig, "0" * 64)):
            with self.assertRaises(lb.Rejected):
                lb.verify_permit(r, s, self.key, pin, lb.digest(lb.encode(bundle)))

    def test_unsigned_declarations_do_not_admit(self):
        bundle, _ = prepared(fixture())
        raw, _ = self.signed(bundle)
        with self.assertRaises(lb.Rejected):
            lb.verify_permit(raw, b"", self.key, lb.digest(self.key), lb.digest(lb.encode(bundle)))

    def test_wrong_scope_dataset_identity_time_or_budget(self):
        bundle, _ = prepared(fixture())
        for change in ({"purpose": "clinical"}, {"requests_sha256": "c" * 64},
                       {"model_revision": "main"}, {"serving_manifest_sha256": ""},
                       {"rights_review": ""}, {"expires_at": "2020-01-01T00:00:00Z"},
                       {"max_cases": True}, {"data_class": "patient"}):
            raw, sig = self.signed(bundle, **change)
            with self.assertRaises(lb.Rejected):
                lb.verify_permit(raw, sig, self.key, lb.digest(self.key), lb.digest(lb.encode(bundle)))

    def test_remote_redirect_and_url_credentials_forbidden(self):
        bundle, _ = prepared(fixture())
        for endpoint in ("https://example.org/v1/chat/completions", "http://localhost:123/v1/chat/completions",
                         "http://127.0.0.1:123/admin", "http://u:p@127.0.0.1:123/v1/chat/completions",
                         "http://127.0.0.1:123/v1/chat/completions?redirect=1"):
            raw, sig = self.signed(bundle, endpoint=endpoint)
            with self.assertRaises(lb.Rejected):
                lb.verify_permit(raw, sig, self.key, lb.digest(self.key), lb.digest(lb.encode(bundle)))

    def test_case_budget(self):
        bundle, _ = prepared(fixture(), fixture(suffix="two"))
        raw, sig = self.signed(bundle, max_cases=1)
        with self.assertRaisesRegex(lb.Rejected, "CASE_BUDGET_EXCEEDED"):
            lb.infer(bundle, raw, sig, self.key, lb.digest(self.key))

    def test_loopback_transport_and_failure_categories(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                body = lb.decode(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append(body)
                count = len(seen)
                obj = {"model": "synthetic-model", "choices": [{"finish_reason": "length" if count == 2 else "stop",
                       "message": {"content": "A", **({"tool_calls": [{"name": "shell"}]} if count == 3 else {})}}]}
                payload = lb.encode(obj)
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        server = HTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            bundle, gold = prepared(*(fixture(suffix=str(i)) for i in range(3)))
            raw, sig = self.signed(bundle, endpoint=f"http://127.0.0.1:{server.server_port}/v1/chat/completions")
            run = lb.infer(bundle, raw, sig, self.key, lb.digest(self.key))
            self.assertEqual([p["status"] for p in run["predictions"]], ["answered", "failed", "failed"])
            self.assertEqual(run["predictions"][1]["error_code"], "INCOMPLETE_GENERATION")
            self.assertEqual(run["predictions"][2]["error_code"], "UNEXPECTED_MODEL_OUTPUT")
            self.assertNotIn("SECRET", str(seen))
            self.assertNotIn("expected", str(seen))
            self.assertEqual(run["serving_identity"], "DECLARED_NOT_ATTESTED")
            report = lb.score(gold, run, lb.digest(lb.encode(gold)))
            self.assertEqual(report["counts"]["failed"], 2)
        finally:
            server.shutdown()
            worker.join()
            server.server_close()


class BoundaryTests(unittest.TestCase):
    def rows(self):
        return [{"split": split, "subject_id": split, "cohort_id": split,
                 "last_observation": f"2026-0{i}-01T00:00:00Z",
                 "anchor": f"2026-0{i}-02T00:00:00Z", "outcome_time": f"2026-0{i}-03T00:00:00Z"}
                for i, split in enumerate(("train", "validation", "test"), 1)]

    def test_valid_longitudinal_split(self):
        self.assertEqual(lb.check_longitudinal_split(self.rows())["status"], "SPLIT_STRUCTURE_VALID")

    def test_subject_and_cohort_leakage(self):
        for field in ("subject_id", "cohort_id"):
            rows = self.rows()
            rows[2][field] = rows[0][field]
            with self.assertRaises(lb.Rejected):
                lb.check_longitudinal_split(rows)

    def test_future_and_target_leakage(self):
        for field in ("last_observation", "anchor"):
            rows = self.rows()
            rows[0][field] = rows[0]["outcome_time"]
            with self.assertRaises(lb.Rejected):
                lb.check_longitudinal_split(rows)

    def test_temporal_overlap(self):
        rows = self.rows()
        rows[0]["outcome_time"] = "2026-02-03T00:00:00Z"
        with self.assertRaisesRegex(lb.Rejected, "TEMPORAL_SPLIT_LEAKAGE"):
            lb.check_longitudinal_split(rows)

    def test_incomplete_split(self):
        with self.assertRaisesRegex(lb.Rejected, "INCOMPLETE_SPLIT"):
            lb.check_longitudinal_split(self.rows()[:2])

    def test_allowed_research_tools(self):
        bundle, gold = prepared(fixture())
        report = lb.score(gold, run_for(bundle, []), lb.digest(lb.encode(gold)))
        result = lb.research_tools([{"tool": "inspect_coverage", "report": "test"},
                                    {"tool": "propose_followup", "report": "test"}], {"test": report})
        self.assertFalse(result["receipts"][1]["result"]["may_publish_to_twin"])

    def test_unqualified_tools_denied(self):
        for tool in ("shell", "aging_clock", "prescribe", "download_model", "publish_to_twin"):
            with self.assertRaisesRegex(lb.Rejected, "TOOL_NOT_QUALIFIED"):
                lb.research_tools([{"tool": tool, "report": "test"}], {})

    def test_step_budget(self):
        with self.assertRaisesRegex(lb.Rejected, "STEP_BUDGET_EXCEEDED"):
            lb.research_tools([{"tool": "inspect_coverage", "report": "test"}] * 7, {})


if __name__ == "__main__":
    unittest.main()
