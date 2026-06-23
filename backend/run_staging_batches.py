#!/usr/bin/env python3
"""Run the lean 14-test staging E2E suite in guarded parallel batches.

Each test runs as its own subprocess (own Chromium, own Playwright) so we get
true concurrency. Headed browser at slow_mo=100 to match the existing
run_5_staging_tests.py defaults. Continues past failures, no pause between
batches, aggregates a final pass/fail report.

Current lean set:
- Normal smoke: 1, 2, 7, 10, 11, 14
- Promo core: 16, 17, 18, 19, 20
- Referral: 23, 24, 25

Promo coverage:
- TEST10 7-day percentage discount.
- FREE100 and FREEWEEK at 7 billing days => £0.
- FREEWEEK at 8 billing days / 01:05 return => deduct AIRPORT_QUOTE_WEEK1_PRICE_PENCE.
- FREE100 at the same 8 billing-day / 01:05 condition => £0.

Per-test stdout/stderr is captured to backend/staging_logs/test_<NN>.log.

Usage:
    python3 run_staging_batches.py             # batches of 2
    python3 run_staging_batches.py --size 2    # batches of 2

Loads DATABASE_URL / STAGING_DATABASE_URL etc. from backend/.env if python-dotenv is present.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# Import TEST_CASES + STAGING_URL just to enumerate names (no Playwright at import).
from create_test_bookings import LEAN_STAGING_TEST_INDEXES, TEST_CASES, STAGING_URL


LOG_DIR = ROOT / "staging_logs"

# Normal smoke can run in small parallel batches. Promo and referral tests stay
# single-file batches to avoid shared code state, reset races, and referral
# attribution writes against the same staging code.
BATCHES = [
    [1, 2],
    [7, 10],
    [11, 14],
    [16],
    [17],
    [18],
    [19],
    [20],
    [23],
    [24],
    [25],
]
assert [idx for batch in BATCHES for idx in batch] == LEAN_STAGING_TEST_INDEXES


def run_one_attempt(test_idx_1based, env_label, browser, device, log_path, headless=True):
    """Run a single test attempt. Appends output to log_path and returns True/False."""
    env = os.environ.copy()
    env["TEST_INDEX"] = str(test_idx_1based)
    env["HEADLESS"] = "true" if headless else "false"
    env["BROWSER"] = browser
    if device:
        env["DEVICE"] = device
    else:
        env.pop("DEVICE", None)

    with open(log_path, "a") as out:
        out.write(f"[{env_label}] browser={browser} device={device or '-'} headless={headless}\n")
        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "create_test_bookings.py")],
                cwd=str(ROOT),
                env=env,
                stdout=out,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=600,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            out.write("\n!! Test exceeded 600s timeout, killed\n")
            return False


def run_one(test_idx_1based, name, env_label, browser, device, log_dir, headless=True, retries=1):
    """Run a single test as a subprocess. Returns (idx, name, ok, duration, log_path)."""
    log_path = log_dir / f"test_{test_idx_1based:02d}.log"
    started = time.time()
    ok = False
    max_attempts = retries + 1

    log_path.write_text("")
    for attempt in range(1, max_attempts + 1):
        with open(log_path, "a") as out:
            out.write("\n" + "=" * 72 + "\n")
            out.write(f"Attempt {attempt}/{max_attempts}: {name}\n")
            out.write("=" * 72 + "\n")

        ok = run_one_attempt(test_idx_1based, env_label, browser, device, log_path, headless)
        if ok:
            break

        if attempt < max_attempts:
            with open(log_path, "a") as out:
                out.write("\n!! Attempt failed; retrying in a fresh browser after 10s\n")
            time.sleep(10)

    duration = time.time() - started
    return test_idx_1based, name, ok, duration, log_path


DEFAULT_MATRIX = [
    # (label, browser, device, environment-tag-posted-to-api)
    ("chromium-desktop", "chromium", None, "stg-chromium"),
    ("firefox-desktop",  "firefox",  None, "stg-firefox"),
    ("webkit-desktop",   "webkit",   None, "stg-webkit"),
    # Mobile envs intentionally excluded for now — the script targets desktop
    # selectors (e.g. the time input is .fill()-able on desktop but readonly
    # on MobileTimePicker), so iPhone/iPad would show 0/25 every run and
    # poison the dashboard. Add back here once mobile selectors are wired up.
    # ("webkit-iphone", "webkit", "iPhone 15 Pro", "stg-iphone"),
    # ("webkit-ipad",   "webkit", "iPad Pro 11",   "stg-ipad"),
]


def post_results_to_api(env_tag, passed, failed, total, duration_seconds, run_type="scheduled"):
    """POST one env's results to the production /api/test-results endpoint.
    No-op (and prints a warning) if PROD_API_URL or TEST_RESULTS_API_KEY are missing.
    """
    api_url = os.environ.get("PROD_API_URL", "").rstrip("/")
    api_key = os.environ.get("TEST_RESULTS_API_KEY", "")
    if not api_url or not api_key:
        print(f"[{env_tag}] Skipping POST — PROD_API_URL or TEST_RESULTS_API_KEY not set")
        return

    payload = {
        "environment": env_tag,           # e.g. "stg-chromium" (must be ≤20 chars)
        "run_type": run_type,
        "tests_passed": int(passed),
        "tests_failed": int(failed),
        "tests_skipped": 0,
        "tests_total": int(total),
        "duration_seconds": int(duration_seconds),
        "commit_sha": os.environ.get("GITHUB_SHA", ""),
        "branch": os.environ.get("E2E_SOURCE_BRANCH", os.environ.get("GITHUB_REF_NAME", "")),
        "logs_url": (
            f"{os.environ.get('GITHUB_SERVER_URL','')}/{os.environ.get('GITHUB_REPOSITORY','')}"
            f"/actions/runs/{os.environ.get('GITHUB_RUN_ID','')}"
            if os.environ.get("GITHUB_RUN_ID")
            else ""
        ),
        "triggered_by": "github_actions" if os.environ.get("GITHUB_ACTIONS") else "manual",
        "api_key": api_key,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{api_url}/api/test-results",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"[{env_tag}] POSTed results → {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"[{env_tag}] POST HTTP {e.code}: {e.read().decode(errors='ignore')[:200]}")
    except Exception as e:
        print(f"[{env_tag}] POST failed: {e}")


def run_one_env(label, browser, device, batch_size, retries=1, env_tag=None, post_results=False):
    """Run the full 25-test suite for one (browser, device) env. Returns list of results."""
    log_dir = ROOT / "staging_logs" / label
    log_dir.mkdir(parents=True, exist_ok=True)
    for old in log_dir.glob("test_*.log"):
        old.unlink()

    print(f"\n##### ENV: {label}  ({browser} / {device or 'desktop'}) #####")
    results = []
    env_started = time.time()

    for batch_idx, indices in enumerate(BATCHES, start=1):
        batch = [(i, TEST_CASES[i - 1]) for i in indices]
        print(f"\n[{label}] Batch {batch_idx}/{len(BATCHES)} (parallel)")
        with ThreadPoolExecutor(max_workers=batch_size) as pool:
            futures = [
                pool.submit(run_one, idx, tc["name"], label, browser, device, log_dir, retries=retries)
                for idx, tc in batch
            ]
            for fut in as_completed(futures):
                idx, name, ok, duration, log_path = fut.result()
                status = "PASS" if ok else "FAIL"
                print(f"   [{label}][{idx:>2}] {status}  ({duration:.0f}s)  {name}")
                results.append((label, idx, name, ok, duration, log_path))

    env_duration = time.time() - env_started
    print(f"\n##### {label} done in {env_duration:.0f}s #####")

    if post_results and env_tag:
        passed = sum(1 for _, _, _, ok, _, _ in results if ok)
        failed = len(results) - passed
        post_results_to_api(env_tag, passed, failed, len(results), env_duration)

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=2, help="parallel workers per batch (default 2)")
    parser.add_argument("--retries", type=int, default=1, help="retry failed tests in a fresh browser (default 1)")
    parser.add_argument("--browser", default=None, help="single env: chromium|firefox|webkit (ignores --matrix)")
    parser.add_argument("--device", default=None, help="single env: Playwright device name")
    parser.add_argument("--matrix", action="store_true", help="run the cross-browser matrix sequentially")
    parser.add_argument("--post-results", action="store_true",
                        help="POST per-env results to PROD_API_URL/api/test-results (used by the cron job)")
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    total_tests_per_env = sum(len(b) for b in BATCHES)
    started_all = time.time()
    all_results = []

    if args.matrix:
        envs = DEFAULT_MATRIX
        print("=" * 72)
        print(f"Staging URL : {STAGING_URL}")
        print(f"Envs        : {len(envs)} (sequential)")
        print(f"Per env     : {total_tests_per_env} tests, parallel batches of {args.size}")
        print(f"Retries     : {args.retries} per failed test")
        print(f"Total tests : {len(envs) * total_tests_per_env}")
        print(f"POST results: {args.post_results}")
        print("=" * 72)
        for label, browser, device, env_tag in envs:
            all_results.extend(
                run_one_env(label, browser, device, args.size,
                            retries=args.retries,
                            env_tag=env_tag, post_results=args.post_results)
            )
    else:
        label = (args.browser or "chromium") + ("-" + (args.device or "desktop").replace(" ", "_").lower())
        all_results.extend(run_one_env(
            label, args.browser or "chromium", args.device, args.size, retries=args.retries,
            env_tag=label[:20], post_results=args.post_results,
        ))

    total_duration = time.time() - started_all
    passed = sum(1 for *_, ok, _, _ in all_results if ok)
    failed = len(all_results) - passed

    print("\n" + "=" * 72)
    print(f"Summary  : {passed}/{len(all_results)} passed  ({failed} failed)  in {total_duration:.0f}s")
    print("=" * 72)

    # Per-env summary
    by_env = {}
    for label, idx, name, ok, duration, log_path in all_results:
        by_env.setdefault(label, []).append((idx, name, ok, duration, log_path))
    for label, rows in by_env.items():
        rows.sort(key=lambda r: r[0])
        env_pass = sum(1 for _, _, ok, _, _ in rows if ok)
        print(f"\n-- {label}: {env_pass}/{len(rows)} passed --")
        for idx, name, ok, duration, log_path in rows:
            marker = "PASS" if ok else "FAIL"
            print(f"  {marker}  [{idx:>2}]  {duration:>5.0f}s  {name}")
            if not ok:
                print(f"          log: {log_path}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
