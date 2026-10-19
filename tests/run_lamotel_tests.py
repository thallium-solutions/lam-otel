#!/usr/bin/env python3
"""Compile and run the @lam/otel package tests in an isolated extlibs tree.

Every ``tests/test_*.lam`` file is compiled with the ``lamc`` found on PATH
against a temporary ``extlibs/@lam/otel`` copy of this repository (the
installed-package boundary) and its standard output is compared with the
``# expect:`` lines of the file. ``--live`` adds the ``tests/live_*.lam``
cases, which export to a real OTLP collector and only run when
``LAMOTEL_LIVE_TESTS=1`` is set (they are reported as skipped otherwise).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


LIB_ROOT = Path(__file__).resolve().parents[1]
COMPILER = "lamc"
MIN_COMPILER_VERSION = (2, 1, 0)
PACKAGE_PATH = Path("@lam") / "otel"
LIVE_SWITCH = "LAMOTEL_LIVE_TESTS"
VERSION_PATTERN = re.compile(r"(?:lamc\s+)?v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?")


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def _check_compiler() -> bool:
    try:
        proc = _run([COMPILER, "version"], cwd=LIB_ROOT, timeout=10)
    except FileNotFoundError:
        print(f"Error: {COMPILER} is not installed or is not on PATH.", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print(f"Error: {COMPILER} version check timed out.", file=sys.stderr)
        return False
    except OSError as exc:
        print(f"Error: unable to run {COMPILER}: {exc}", file=sys.stderr)
        return False

    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit status {proc.returncode}"
        print(f"Error: unable to check {COMPILER} version: {detail}", file=sys.stderr)
        return False

    version_text = proc.stdout.strip()
    match = VERSION_PATTERN.fullmatch(version_text)
    if not match:
        print(f"Error: {COMPILER} returned an invalid version: {version_text!r}.", file=sys.stderr)
        return False

    version = tuple(int(part) for part in match.groups())
    if version < MIN_COMPILER_VERSION:
        required = ".".join(str(part) for part in MIN_COMPILER_VERSION)
        print(
            f"Error: {COMPILER} {version_text} is incompatible; version >= {required} is required.",
            file=sys.stderr,
        )
        return False
    return True


def _expectations(source: str) -> list[str]:
    return [
        match.group(1).strip()
        for line in source.splitlines()
        if (match := re.match(r"^\s*#\s*expect:\s*(.*)$", line))
    ]


def _stage_package(extlibs: Path) -> None:
    destination = extlibs / PACKAGE_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        LIB_ROOT,
        destination,
        ignore=shutil.ignore_patterns(
            ".git",
            "build",
            "extlibs",
            "tests",
            "*.lamc-cache",
            "__pycache__",
            "*.pyc",
        ),
    )


def _process_failure(label: str, proc: subprocess.CompletedProcess[str]) -> str:
    details = [f"{label} ({proc.returncode})"]
    if proc.stdout.strip():
        details.append("stdout:\n" + proc.stdout.rstrip())
    if proc.stderr.strip():
        details.append("stderr:\n" + proc.stderr.rstrip())
    return "\n".join(details)


def _test_env() -> dict[str, str]:
    # Tests configure the SDK explicitly; ambient OTEL_* settings of the
    # developer's shell must not leak into the offline cases.
    env = {key: value for key, value in os.environ.items() if not key.startswith("OTEL_")}
    return env


def _run_case(path: Path, *, live: bool) -> tuple[bool, str]:
    expected = _expectations(path.read_text(encoding="utf-8"))
    if not expected:
        return False, "TEST ERROR: no '# expect:' lines found"

    with tempfile.TemporaryDirectory(prefix="lamotel_test_") as tmp:
        root = Path(tmp)
        extlibs = root / "extlibs"
        _stage_package(extlibs)
        binary = root / "test_binary"
        command = [
            COMPILER,
            str(path),
            "--extlibs",
            str(extlibs),
            "--no-cache",
            "-o",
            str(binary),
        ]
        try:
            compile_proc = _run(command, cwd=root, timeout=300)
        except subprocess.TimeoutExpired:
            return False, "COMPILE FAIL: timed out after 300 seconds"
        except OSError as exc:
            return False, f"COMPILE FAIL: unable to run {COMPILER}: {exc}"
        if compile_proc.returncode != 0:
            return False, _process_failure("COMPILE FAIL", compile_proc)

        env = os.environ.copy() if live else _test_env()
        try:
            run_proc = _run([str(binary)], cwd=root, timeout=120, env=env)
        except subprocess.TimeoutExpired:
            return False, "RUN FAIL: timed out after 120 seconds"
        except OSError as exc:
            return False, f"RUN FAIL: unable to execute test binary: {exc}"
        if run_proc.returncode != 0:
            return False, _process_failure("RUN FAIL", run_proc)

        actual = run_proc.stdout.rstrip("\n")
        expected_text = "\n".join(expected)
        if actual != expected_text:
            return (
                False,
                "OUTPUT MISMATCH:\n"
                f"  expected: {expected_text!r}\n"
                f"  actual:   {actual!r}"
                + (f"\n  stderr:   {run_proc.stderr.rstrip()!r}" if run_proc.stderr else ""),
            )
        return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="@lam/otel package tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="show full failure details")
    parser.add_argument(
        "--live",
        action="store_true",
        help=f"also run tests/live_*.lam against a real collector (requires {LIVE_SWITCH}=1)",
    )
    parser.add_argument(
        "--filter",
        "-k",
        default="",
        help="only run test files whose name contains this text",
    )
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=1,
        help="number of test files compiled and run in parallel (default: 1)",
    )
    args = parser.parse_args()

    if not _check_compiler():
        return 1

    cases = sorted((LIB_ROOT / "tests").glob("test_*.lam"))
    live_cases = sorted((LIB_ROOT / "tests").glob("live_*.lam")) if args.live else []
    if args.filter:
        cases = [case for case in cases if args.filter in case.name]
        live_cases = [case for case in live_cases if args.filter in case.name]
    if not cases and not live_cases:
        print("Error: no @lam/otel test cases found.", file=sys.stderr)
        return 1

    skipped: list[Path] = []
    if live_cases and os.environ.get(LIVE_SWITCH, "") != "1":
        skipped = live_cases
        live_cases = []

    selected = [(case, False) for case in cases] + [(case, True) for case in live_cases]
    failures: list[tuple[Path, str]] = []
    total = len(selected) + len(skipped)
    print(f"Running {total} @lam/otel test(s)...\n")

    def run(item: tuple[Path, bool]) -> tuple[Path, bool, str]:
        case, live = item
        ok, message = _run_case(case, live=live)
        return case, ok, message

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for case, ok, message in pool.map(run, selected):
            relative = case.relative_to(LIB_ROOT)
            print(f"  {'PASS' if ok else 'FAIL'}  {relative}", flush=True)
            if not ok:
                failures.append((relative, message))
                if args.verbose:
                    for line in message.splitlines():
                        print(f"        {line}")
    for case in skipped:
        print(f"  SKIP  {case.relative_to(LIB_ROOT)} (set {LIVE_SWITCH}=1)")

    passed = len(selected) - len(failures)
    print(
        f"\n@lam/otel results: {passed} passed, {len(failures)} failed, "
        f"{len(skipped)} skipped, {total} total"
    )
    if failures and not args.verbose:
        print("Re-run with --verbose for failure details.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
