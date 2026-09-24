"""Research-only LongevityBench adapter. No upstream code, weights or clinical writes.

Python 3.11+ standard library; signed inference permits additionally need OpenSSL
with Ed25519 support. This scorer is NOT an official leaderboard reproduction.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import math
import re
import statistics
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
SCHEMA = "openbody.longevity.research.v1"
PARSER = "strict-final-answer-v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
MAX_FILE = 256 * 1024 * 1024
MAX_RESPONSE = 4 * 1024 * 1024


class Rejected(ValueError):
    """A stable, non-sensitive rejection code."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise Rejected(code)


def encode(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def decode(data: bytes | str) -> Any:
    def nonfinite(_: str) -> None:
        raise Rejected("NONFINITE_JSON")
    def finite_float(text: str) -> float:
        value = float(text)
        require(math.isfinite(value), "NONFINITE_JSON")
        return value
    try:
        return json.loads(data, object_pairs_hook=_object, parse_constant=nonfinite, parse_float=finite_float)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Rejected("INVALID_JSON") from exc


def read_bytes(path: Path, limit: int = MAX_FILE) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, "FILE_TOO_LARGE")
    return data


def write_new(path: Path, value: Any) -> None:
    # Never replace an existing experiment or follow a destination symlink.
    with path.open("xb") as stream:
        stream.write(encode(value) + b"\n")


def catalog() -> dict:
    return decode(read_bytes(HERE / "catalog.json"))


def spec_for(row: dict, config: str) -> dict:
    require(config in {"benchmark", "mini"}, "UNSUPPORTED_CONFIG")
    for spec in catalog()["tasks"]:
        if row.get("lb_id") == spec["id" if config == "benchmark" else "mini_id"]:
            require(all(row.get(k) == spec[k] for k in ("pool", "domain", "format", "metric")),
                    "TASK_SCHEMA_DRIFT")
            require(row.get("units") == spec["units"], "TASK_UNITS_DRIFT")
            return spec
    raise Rejected("UNSUPPORTED_TASK")


def answer(text: Any, metric: str) -> str | float:
    require(isinstance(text, str) and len(text) <= MAX_RESPONSE, "INVALID_ANSWER")
    # Some released checkpoints put the reasoning terminator in content.
    text = text.rsplit("</think>", 1)[-1].strip()
    if metric == "mae":
        require(bool(NUMBER.fullmatch(text)), "INVALID_NUMERIC_ANSWER")
        value = float(text)
        require(math.isfinite(value) and abs(value) <= 1e9, "NONFINITE_OR_EXTREME_ANSWER")
        return value
    require(metric == "accuracy", "UNSUPPORTED_METRIC")
    require(bool(re.fullmatch(r"[A-Z]|[01]|yes|no|true|false", text)), "INVALID_CLASS_ANSWER")
    return text


def case_id(pool: str, messages: list[dict]) -> str:
    # Gold, metadata, and config-specific task IDs are deliberately excluded.
    return digest(encode({"pool": pool, "messages": messages}))


def prepare(raw: bytes, expected_sha256: str, config: str, *, synthetic: bool = False,
            rights_review: str = "") -> tuple[dict, dict]:
    require(bool(HEX.fullmatch(expected_sha256)), "INVALID_DIGEST")
    require(digest(raw) == expected_sha256, "ARTIFACT_DIGEST_MISMATCH")
    require(synthetic or bool(rights_review.strip()), "RIGHTS_REVIEW_REQUIRED")
    requests, labels, seen = [], [], set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        row = decode(line)
        require(isinstance(row, dict), "INVALID_ROW")
        spec = spec_for(row, config)
        messages = row.get("messages")
        require(isinstance(messages, list) and len(messages) == 3, "UNSUPPORTED_CHAT_SHAPE")
        require(all(isinstance(m, dict) and set(m) == {"role", "content"}
                    and isinstance(m["content"], str) and bool(m["content"].strip())
                    for m in messages), "UNSUPPORTED_MESSAGE_FIELDS")
        require([m["role"] for m in messages] == ["system", "user", "assistant"],
                "UNSUPPORTED_CHAT_ROLES")
        prompt = [dict(m) for m in messages[:2]]
        identifier = case_id(spec["pool"], prompt)
        require(identifier not in seen, "DUPLICATE_PROMPT")
        seen.add(identifier)
        requests.append({"id": identifier, "pool": spec["pool"], "messages": prompt})
        labels.append({"id": identifier, "pool": spec["pool"], "domain": spec["domain"],
                       "metric": spec["metric"], "units": spec["units"],
                       "expected": answer(messages[-1]["content"], spec["metric"])})
    require(bool(requests), "EMPTY_DATASET")
    shared = {"schema": SCHEMA, "config": config, "source_sha256": expected_sha256,
              "data_class": "synthetic" if synthetic else "public_benchmark",
              "rights_review": rights_review, "catalog_sha256": digest(read_bytes(HERE / "catalog.json"))}
    blinded = {**shared, "requests": requests}
    gold = {**shared, "requests_sha256": digest(encode(blinded)), "labels": labels}
    return blinded, gold


def validate_requests(bundle: dict) -> None:
    require(isinstance(bundle, dict) and bundle.get("schema") == SCHEMA, "INVALID_REQUEST_BUNDLE")
    require(bundle.get("data_class") in {"synthetic", "public_benchmark"}, "PRIVATE_DATA_FORBIDDEN")
    require(isinstance(bundle.get("requests"), list) and bool(bundle["requests"]), "EMPTY_DATASET")
    seen = set()
    for item in bundle["requests"]:
        require(isinstance(item, dict) and set(item) == {"id", "pool", "messages"}, "INVALID_REQUEST")
        messages = item["messages"]
        require(isinstance(messages, list) and len(messages) == 2, "INVALID_PROMPT")
        require(all(isinstance(m, dict) and set(m) == {"role", "content"}
                    and isinstance(m["content"], str) for m in messages), "INVALID_PROMPT")
        require([m["role"] for m in messages] == ["system", "user"], "INVALID_PROMPT_ROLES")
        require(item["id"] == case_id(item["pool"], messages), "PROMPT_DIGEST_MISMATCH")
        require(item["id"] not in seen, "DUPLICATE_PROMPT")
        seen.add(item["id"])


def score(gold: dict, run: dict, expected_gold_sha256: str) -> dict:
    require(bool(HEX.fullmatch(expected_gold_sha256)) and digest(encode(gold)) == expected_gold_sha256,
            "GOLD_DIGEST_MISMATCH")
    require(gold.get("schema") == SCHEMA and run.get("schema") == SCHEMA, "SCHEMA_MISMATCH")
    require(gold["requests_sha256"] == run.get("requests_sha256"), "RUN_DATASET_MISMATCH")
    labels = gold.get("labels", [])
    require(bool(labels), "EMPTY_GOLD")
    ids = [r["id"] for r in labels]
    require(len(ids) == len(set(ids)), "DUPLICATE_GOLD")
    known_ids = set(ids)
    predictions = {}
    for pred in run.get("predictions", []):
        require(isinstance(pred, dict) and pred.get("id") in known_ids, "UNKNOWN_PREDICTION")
        require(pred["id"] not in predictions, "DUPLICATE_PREDICTION")
        require(pred.get("status") in {"answered", "abstained", "failed", "invalid"}, "INVALID_STATUS")
        require(pred["status"] == "answered" or pred.get("answer") is None, "NONANSWER_HAS_VALUE")
        predictions[pred["id"]] = pred
    groups = defaultdict(list)
    for row in labels:
        groups[row["pool"]].append(row)
    tasks = {}
    for pool, rows in sorted(groups.items()):
        metric, units, domain = (rows[0][k] for k in ("metric", "units", "domain"))
        require(metric in {"accuracy", "mae"}, "UNSUPPORTED_METRIC")
        require(all((r["metric"], r["units"], r["domain"]) == (metric, units, domain)
                    for r in rows), "MIXED_TASK_SCHEMA")
        counts, correct, errors, totals, hits = Counter(), 0, [], Counter(), Counter()
        for row in rows:
            expected = answer(str(row["expected"]), metric)
            if metric == "accuracy":
                totals[expected] += 1
            pred = predictions.get(row["id"], {"status": "missing"})
            state = pred["status"]
            parsed = None
            if state == "answered":
                try:
                    parsed = answer(pred.get("answer"), metric)
                except Rejected:
                    state = "invalid"
            counts[state] += 1
            if state == "answered":
                if metric == "accuracy":
                    correct += parsed == expected
                    hits[expected] += parsed == expected
                else:
                    errors.append(abs(parsed - expected))
        n, answered = len(rows), counts["answered"]
        result = {"domain": domain, "metric": metric, "units": units, "n": n,
                  "counts": {k: counts[k] for k in ("answered", "abstained", "failed", "invalid", "missing")},
                  "coverage": answered / n}
        if metric == "accuracy":
            result.update(accuracy=correct / n,
                          selective_accuracy=correct / answered if answered else None,
                          balanced_accuracy=statistics.mean(hits[c] / totals[c] for c in totals))
        else:
            conditional = statistics.mean(errors) if errors else None
            result.update(mae=conditional if answered == n else None, selective_mae=conditional)
        tasks[pool] = result
    expected_counts = {s["pool"]: s["n" if gold["config"] == "benchmark" else "mini_n"]
                       for s in catalog()["tasks"]}
    complete = {p: t["n"] for p, t in tasks.items()} == expected_counts
    totals = {k: sum(t["counts"][k] for t in tasks.values())
              for k in ("answered", "abstained", "failed", "invalid", "missing")}
    return {"schema": SCHEMA, "kind": "research_scorecard", "parser": PARSER,
            "clinical_use": False, "official_reproduction": False,
            "data_class": gold["data_class"], "config": gold["config"],
            "complete_task_counts": complete, "tasks": tasks, "counts": totals,
            "gold_sha256": digest(encode(gold)), "run_sha256": digest(encode(run)),
            "requests_sha256": gold["requests_sha256"], "code_sha256": digest(read_bytes(Path(__file__))),
            "promotion": "BLOCKED_RESEARCH_ONLY"}



def compare(gold: dict, baseline: dict, candidate: dict, expected_gold_sha256: str) -> dict:
    """Same-case per-task comparison; no pooled rank or statistical superiority claim."""
    left = score(gold, baseline, expected_gold_sha256)
    right = score(gold, candidate, expected_gold_sha256)
    changes = {}
    for pool, a in left["tasks"].items():
        b = right["tasks"][pool]
        key = "mae" if a["metric"] == "mae" else "accuracy"
        both_complete = a["coverage"] == b["coverage"] == 1
        delta = None
        if both_complete:
            delta = a[key] - b[key] if key == "mae" else b[key] - a[key]
        changes[pool] = {"metric": key, "units": a["units"], "baseline": a[key],
                         "candidate": b[key], "improvement": delta,
                         "comparable_full_coverage": both_complete}
    return {"schema": SCHEMA, "kind": "research_comparison", "tasks": changes,
            "baseline_run_sha256": left["run_sha256"], "candidate_run_sha256": right["run_sha256"],
            "requests_sha256": gold["requests_sha256"], "clinical_use": False,
            "superiority_established": False, "uncertainty_analysis": "NOT_IMPLEMENTED",
            "official_reproduction": False}


def verify_permit(raw: bytes, signature: bytes, public_key: bytes, key_pin: str,
                  requests_sha256: str, now: datetime | None = None) -> dict:
    """Verify a maintainer authorization, not publisher authenticity or model attestation."""
    require(bool(HEX.fullmatch(key_pin)) and digest(public_key) == key_pin, "UNTRUSTED_KEY")
    require(len(raw) <= 16384 and len(signature) == 64, "INVALID_SIGNATURE_INPUT")
    try:
        pem = public_key.decode("ascii").strip().splitlines()
        require(pem[0] == "-----BEGIN PUBLIC KEY-----" and pem[-1] == "-----END PUBLIC KEY-----",
                "INVALID_PUBLIC_KEY")
        der = base64.b64decode("".join(pem[1:-1]), validate=True)
        require(len(der) == 44 and der[:12] == bytes.fromhex("302a300506032b6570032100"),
                "ED25519_REQUIRED")
    except (ValueError, UnicodeError, IndexError) as exc:
        raise Rejected("INVALID_PUBLIC_KEY") from exc
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name, data in (("permit", raw), ("sig", signature), ("key", public_key)):
            (root / name).write_bytes(data)
        try:
            check = subprocess.run(["/usr/bin/openssl", "pkeyutl", "-verify", "-pubin", "-rawin",
                                    "-inkey", str(root / "key"), "-in", str(root / "permit"),
                                    "-sigfile", str(root / "sig")], capture_output=True, timeout=10,
                                   env={"PATH": "/usr/bin:/bin"}, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Rejected("SIGNATURE_VERIFIER_UNAVAILABLE") from exc
    require(check.returncode == 0, "INVALID_SIGNATURE")
    permit = decode(raw)
    require(isinstance(permit, dict) and permit.get("schema") == "openbody.longevity.permit.v1",
            "INVALID_PERMIT")
    require(permit.get("purpose") == "public-benchmark-inference", "INVALID_PURPOSE")
    require(permit.get("requests_sha256") == requests_sha256, "PERMIT_DATASET_MISMATCH")
    require(permit.get("data_class") in {"synthetic", "public_benchmark"}, "PRIVATE_DATA_FORBIDDEN")
    for field in ("rights_review", "provenance_review", "reviewer", "model"):
        require(isinstance(permit.get(field), str) and bool(permit[field].strip()), "INCOMPLETE_REVIEW")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", permit.get("model_revision", ""))), "UNPINNED_MODEL")
    require(bool(HEX.fullmatch(permit.get("serving_manifest_sha256", ""))), "UNPINNED_SERVING_MANIFEST")
    require(type(permit.get("max_cases")) is int and 1 <= permit["max_cases"] <= 25457, "INVALID_BUDGET")
    try:
        start = datetime.fromisoformat(permit["not_before"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(permit["expires_at"].replace("Z", "+00:00"))
        require(start.tzinfo is not None and end.tzinfo is not None, "NAIVE_PERMIT_TIME")
        require(start <= (now or datetime.now(timezone.utc)) < end, "PERMIT_NOT_CURRENT")
    except (KeyError, TypeError, ValueError) as exc:
        raise Rejected("PERMIT_TIME_INVALID") from exc
    endpoint = urlsplit(permit.get("endpoint", ""))
    require(endpoint.scheme == "http" and endpoint.hostname == "127.0.0.1"
            and endpoint.path == "/v1/chat/completions" and endpoint.port is not None
            and endpoint.username is None and endpoint.password is None
            and not endpoint.query and not endpoint.fragment, "NONLOCAL_ENDPOINT")
    return permit


def infer(bundle: dict, permit_raw: bytes, signature: bytes, key: bytes, key_pin: str) -> dict:
    validate_requests(bundle)
    request_hash = digest(encode(bundle))
    permit = verify_permit(permit_raw, signature, key, key_pin, request_hash)
    require(bundle["data_class"] == permit["data_class"], "PERMIT_DATA_CLASS_MISMATCH")
    require(len(bundle["requests"]) <= permit["max_cases"], "CASE_BUDGET_EXCEEDED")
    url = urlsplit(permit["endpoint"])
    predictions = []
    for item in bundle["requests"]:
        # Recheck expiry before every effect. No redirects, proxies, shell or tool execution.
        verify_permit(permit_raw, signature, key, key_pin, request_hash)
        body = encode({"model": permit["model"], "messages": item["messages"],
                       "temperature": 0, "max_tokens": 2048, "stream": False})
        start = time.monotonic()
        connection = http.client.HTTPConnection("127.0.0.1", url.port, timeout=60)
        pred = {"id": item["id"], "status": "failed", "answer": None}
        try:
            connection.request("POST", url.path, body=body, headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            require(response.status == 200, "HTTP_STATUS")
            data = response.read(MAX_RESPONSE + 1)
            require(len(data) <= MAX_RESPONSE, "RESPONSE_TOO_LARGE")
            obj = decode(data)
            require(obj.get("model") == permit["model"], "SERVED_MODEL_MISMATCH")
            require(len(obj.get("choices", [])) == 1, "INVALID_CHOICES")
            choice = obj["choices"][0]
            require(choice.get("finish_reason") == "stop", "INCOMPLETE_GENERATION")
            message = choice["message"]
            require(not message.get("tool_calls") and isinstance(message.get("content"), str),
                    "UNEXPECTED_MODEL_OUTPUT")
            verify_permit(permit_raw, signature, key, key_pin, request_hash)
            pred.update(status="answered", answer=message["content"])
        except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError, AttributeError) as exc:
            pred["error_code"] = str(exc) if isinstance(exc, Rejected) else "EXECUTION_FAILED"
        finally:
            connection.close()
        pred["latency_ms"] = round((time.monotonic() - start) * 1000, 3)
        predictions.append(pred)
    return {"schema": SCHEMA, "requests_sha256": request_hash, "predictions": predictions,
            "model": permit["model"], "model_revision": permit["model_revision"],
            "serving_manifest_sha256": permit["serving_manifest_sha256"],
            "permit_sha256": digest(permit_raw), "serving_identity": "DECLARED_NOT_ATTESTED",
            "decoding": {"temperature": 0, "max_tokens": 2048}, "clinical_use": False}


def check_longitudinal_split(rows: list[dict]) -> dict:
    """Validate a NEW subject/cohort-disjoint forward-time study, not LongevityBench."""
    subjects, cohorts, splits = defaultdict(set), defaultdict(set), defaultdict(list)
    require(bool(rows), "EMPTY_SPLIT")
    for row in rows:
        require(row.get("split") in {"train", "validation", "test"}, "INVALID_SPLIT")
        require(bool(row.get("subject_id")) and bool(row.get("cohort_id")), "MISSING_GROUP_ID")
        times = [datetime.fromisoformat(row[k].replace("Z", "+00:00"))
                 for k in ("last_observation", "anchor", "outcome_time")]
        require(all(t.tzinfo is not None for t in times), "NAIVE_TIME")
        require(times[0] <= times[1] < times[2], "FUTURE_OR_TARGET_LEAKAGE")
        subjects[row["subject_id"]].add(row["split"])
        cohorts[row["cohort_id"]].add(row["split"])
        splits[row["split"]].append(times)
    require(set(splits) == {"train", "validation", "test"}, "INCOMPLETE_SPLIT")
    require(all(len(s) == 1 for s in subjects.values()), "SUBJECT_LEAKAGE")
    require(all(len(s) == 1 for s in cohorts.values()), "COHORT_LEAKAGE")
    for earlier, later in (("train", "validation"), ("validation", "test")):
        require(max(t[2] for t in splits[earlier]) < min(t[1] for t in splits[later]),
                "TEMPORAL_SPLIT_LEAKAGE")
    return {"status": "SPLIT_STRUCTURE_VALID", "clinical_validation": False}


def research_tools(plan: list[dict], reports: dict[str, dict], max_steps: int = 6) -> dict:
    """Bounded tool boundary for a Kline planner; no arbitrary third-party tools."""
    require(type(max_steps) is int and 1 <= max_steps <= 6, "INVALID_STEP_BUDGET")
    require(isinstance(plan, list) and 0 < len(plan) <= max_steps, "STEP_BUDGET_EXCEEDED")
    receipts = []
    for step in plan:
        require(isinstance(step, dict) and set(step) == {"tool", "report"}, "INVALID_TOOL_REQUEST")
        require(step["tool"] in {"inspect_coverage", "propose_followup"}, "TOOL_NOT_QUALIFIED")
        require(step["report"] in reports, "UNKNOWN_REPORT")
        report = reports[step["report"]]
        require(report.get("kind") == "research_scorecard" and report.get("clinical_use") is False,
                "INVALID_RESEARCH_REPORT")
        if step["tool"] == "inspect_coverage":
            result = {"counts": report["counts"], "complete_task_counts": report["complete_task_counts"]}
        else:
            result = {"proposal_only": True, "next_gate": "RIGHTS_PROVENANCE_SCORER_PARITY_AND_HOLDOUTS",
                      "may_publish_to_twin": False, "may_recommend_interventions": False}
        receipts.append({"tool": step["tool"], "report_sha256": digest(encode(report)), "result": result})
    return {"schema": SCHEMA, "receipts": receipts, "authority": "RESEARCH_ONLY"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("hash-json")
    p.add_argument("file", type=Path)
    p = commands.add_parser("prepare")
    p.add_argument("raw", type=Path)
    p.add_argument("--sha256", required=True)
    p.add_argument("--config", choices=["benchmark", "mini"], required=True)
    p.add_argument("--rights-review", required=True)
    p.add_argument("--out", type=Path, required=True)
    p = commands.add_parser("run")
    for name in ("requests", "permit", "signature", "key"):
        p.add_argument(name, type=Path)
    p.add_argument("--key-sha256", required=True)
    p.add_argument("--out", type=Path, required=True)
    p = commands.add_parser("score")
    p.add_argument("gold", type=Path)
    p.add_argument("run", type=Path)
    p.add_argument("--gold-sha256", required=True)
    p.add_argument("--out", type=Path, required=True)
    p = commands.add_parser("compare")
    for name in ("gold", "baseline", "candidate"):
        p.add_argument(name, type=Path)
    p.add_argument("--gold-sha256", required=True)
    p.add_argument("--out", type=Path, required=True)
    p = commands.add_parser("check-split")
    p.add_argument("rows", type=Path)
    p = commands.add_parser("tools")
    p.add_argument("plan", type=Path)
    p.add_argument("reports", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "hash-json":
            print(digest(encode(decode(read_bytes(args.file)))))
        elif args.command == "prepare":
            blinded, gold = prepare(read_bytes(args.raw), args.sha256, args.config, rights_review=args.rights_review)
            args.out.mkdir(parents=True, exist_ok=False)
            write_new(args.out / "requests.json", blinded)
            write_new(args.out / "gold.json", gold)
        elif args.command == "run":
            result = infer(decode(read_bytes(args.requests)), read_bytes(args.permit, 16384),
                           read_bytes(args.signature, 64), read_bytes(args.key, 4096), args.key_sha256)
            write_new(args.out, result)
        elif args.command == "score":
            write_new(args.out, score(decode(read_bytes(args.gold)), decode(read_bytes(args.run)), args.gold_sha256))
        elif args.command == "compare":
            write_new(args.out, compare(decode(read_bytes(args.gold)), decode(read_bytes(args.baseline)),
                                        decode(read_bytes(args.candidate)), args.gold_sha256))
        elif args.command == "check-split":
            print(json.dumps(check_longitudinal_split(decode(read_bytes(args.rows))), indent=2))
        else:
            write_new(args.out, research_tools(decode(read_bytes(args.plan)), decode(read_bytes(args.reports))))
    except (Rejected, OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, (str(exc) if isinstance(exc, Rejected) else "INVALID_INPUT_OR_IO") + "\n")


if __name__ == "__main__":
    main()
