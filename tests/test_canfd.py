#!/usr/bin/env python3
"""Focused native simulations for FiCo4OMNeT CAN and CAN-FD behavior."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass


ROOT = pathlib.Path(__file__).resolve().parents[1]
FICO = ROOT / "upstream" / "FiCo4OMNeT"
CANFD_EXAMPLE = FICO / "examples" / "can" / "canfd"
ARBITRATION_EXAMPLE = FICO / "examples" / "can" / "arbitration"
FIXTURE_INI = ROOT / "tests" / "canfd" / "arbitration.ini"


@dataclass
class Run:
    name: str
    returncode: int
    output: str
    results: pathlib.Path


def run_simulation(name: str, directory: pathlib.Path, ini: pathlib.Path,
                   config: str, extra: tuple[str, ...] = ()) -> Run:
    """Run one Cmdenv configuration with the workspace's configured runtime."""
    result_dir = directory / name
    result_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "bash", "-c",
        'set -e; source "$1/scripts/env.sh"; set -u; '
        'cd "$2"; '
        'exec opp_run -u Cmdenv '
        '-n "$3/src:$3/examples" '
        '-l "$3/src/FiCo4OMNeT" '
        '-f "$4" -c "$5" --result-dir="$6" "${@:7}"',
        "canfd-runner", str(ROOT), str(directory), str(FICO), str(ini),
        config, str(result_dir), *extra,
    ]
    completed = subprocess.run(cmd, cwd=ROOT, text=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, check=False)
    (directory / f"{name}.log").write_text(completed.stdout)
    return Run(name, completed.returncode, completed.stdout, result_dir)


def scalar_data(run: Run) -> tuple[dict[tuple[str, str], float], str]:
    """Read scalar and statistic mean records from OMNeT++ result files."""
    paths = list(run.results.glob("*.sca"))
    if len(paths) != 1:
        raise AssertionError(f"{run.name}: expected one .sca, found {paths}")
    text = paths[0].read_text(errors="replace")
    values: dict[tuple[str, str], float] = {}
    scalar_re = re.compile(r"^scalar (\S+) (\S+) (\S+)$")
    stat_re = re.compile(r"^statistic (\S+) (\S+):stats$")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = scalar_re.match(line)
        if match:
            module, name, value = match.groups()
            try:
                values[(module, name)] = float(value)
            except ValueError:
                continue
        match = stat_re.match(line)
        if match:
            module, name = match.groups()
            for following in lines[index + 1:]:
                if following.startswith("field mean "):
                    try:
                        values[(module, name + ":mean")] = float(following.split()[-1])
                    except ValueError:
                        pass
                    break
                if following.startswith(("statistic ", "scalar ", "par ")):
                    break
    return values, text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=pathlib.Path,
                        help="keep raw logs and result files here")
    args = parser.parse_args()
    output = (args.output_dir or ROOT / "results" / "canfd").resolve()
    output.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, object]] = []
    runs: dict[str, Run] = {}
    values: dict[str, dict[tuple[str, str], float]] = {}
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        checks.append({"assertion": label, "passed": bool(condition), "detail": detail})
        print(f"{'PASS' if condition else 'FAIL'} {label}" + (f": {detail}" if detail else ""))
        if not condition:
            failures.append(label + (f": {detail}" if detail else ""))

    def successful_run(name: str, ini: pathlib.Path, config: str,
                       extra: tuple[str, ...] = ()) -> Run:
        run = run_simulation(name, output, ini, config, extra)
        runs[name] = run
        check(f"{name} exits successfully", run.returncode == 0,
              "" if run.returncode == 0 else run.output[-1400:].strip())
        if run.returncode == 0:
            try:
                values[name], _ = scalar_data(run)
            except Exception as error:  # Preserve the failed assertion and continue the suite.
                check(f"{name} has readable scalar results", False, str(error))
        return run

    def scalar(name: str, module: str, stat: str) -> float | None:
        return values.get(name, {}).get((module, stat))

    brs_off = successful_run("brs-off", CANFD_EXAMPLE / "omnetpp.ini", "BRSOff")
    brs_on = successful_run("brs-on", CANFD_EXAMPLE / "omnetpp.ini", "BRSOn")
    for name in ("brs-off", "brs-on"):
        delivered = scalar(name, "CanFd.receiver.sinkApp[0]", "rxDF:count")
        check(f"{name} delivers a CAN-FD frame", delivered == 1,
              f"receiver rxDF count={delivered}")
    off_delay = scalar("brs-off", "CanFd.receiver.sinkApp[0]", "rxDFLatency:mean")
    on_delay = scalar("brs-on", "CanFd.receiver.sinkApp[0]", "rxDFLatency:mean")
    check("BRS-on CAN-FD delivery is faster", off_delay is not None and on_delay is not None
          and on_delay < off_delay, f"BRS off={off_delay}, BRS on={on_delay} seconds")

    expected_rejections = {
        "invalid-payload": "Invalid CAN FD payload length 63",
        "invalid-fd-remote": "CAN FD remote frames are not supported",
    }
    for name, expected_error in expected_rejections.items():
        config = "InvalidPayload" if name == "invalid-payload" else "InvalidFdRemote"
        run = run_simulation(name, output, CANFD_EXAMPLE / "omnetpp.ini", config)
        runs[name] = run
        check(f"{name} is rejected", run.returncode != 0 and expected_error in run.output,
              f"exit={run.returncode}; expected {expected_error!r}; "
              + run.output[-1000:].strip())

    mixed = successful_run("mixed-11-29", FIXTURE_INI, "Mixed11And29")
    if mixed.returncode == 0 and "mixed-11-29" in values:
        received = scalar("mixed-11-29", "Canbus.bus.canBusLogic", "rxDF:count")
        check("simultaneous standard and extended IDs with same 11-bit prefix both arbitrate",
              received == 2, f"bus rxDF count={received}")
        standard_order = read_arbitration_order(mixed)
        check("standard ID wins arbitration over extended ID with matching 11-bit prefix",
              standard_order == [1, 262147],
              f"observed bus ID vector={standard_order}")

    duplicates = run_simulation("duplicate-owners", output, FIXTURE_INI, "DuplicateOwners")
    runs["duplicate-owners"] = duplicates
    collision_error = "Multiple nodes requested the same CAN arbitration identifier and format"
    check("simultaneous duplicate-ID owners report unsupported collision modeling",
          duplicates.returncode != 0 and collision_error in duplicates.output,
          f"exit={duplicates.returncode}; "
          + next((line.strip() for line in duplicates.output.splitlines()
                  if collision_error in line), "expected collision diagnostic absent"))

    queued = successful_run("queued-periodic-same-id", FIXTURE_INI, "QueuedPeriodicSameId")
    if queued.returncode == 0 and "queued-periodic-same-id" in values:
        sent = scalar("queued-periodic-same-id", "Canbus.node[0].sourceApp[0]", "txDF:count")
        received = scalar("queued-periodic-same-id", "Canbus.bus.canBusLogic", "rxDF:count")
        check("periodic same-ID frames queue and make progress under congestion",
              sent is not None and received is not None and received > 1 and sent >= received,
              f"generated={sent}, bus delivered={received}")

    # Run the upstream legacy classic arbitration example with a hard simulated-time bound.
    legacy = successful_run("legacy-classic", ARBITRATION_EXAMPLE / "omnetpp.ini", "General",
                            ("--sim-time-limit=1s", "--vector-recording=false"))
    if legacy.returncode == 0 and "legacy-classic" in values:
        delivered = scalar("legacy-classic", "Canbus.bus.canBusLogic", "rxDF:count")
        check("legacy classic arbitration delivers frames within 1 simulated second",
              delivered is not None and delivered > 0, f"bus rxDF count={delivered}")

    report = {"output_dir": str(output), "checks": checks, "failures": failures}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


def read_arbitration_order(run: Run) -> list[int] | None:
    """Return the bus's CAN-ID receive vector when OMNeT++ recorded it."""
    paths = list(run.results.glob("*.vec"))
    if len(paths) != 1:
        return None
    vector_ids: set[int] = set()
    values: list[tuple[int, float, int]] = []
    for line in paths[0].read_text(errors="replace").splitlines():
        if line.startswith("vector "):
            fields = shlex.split(line)
            if (len(fields) >= 5 and fields[2] == "Canbus.bus.canBusLogic"
                    and fields[3].startswith("rxCANIdDF")):
                vector_ids.add(int(fields[1]))
        elif line and line[0].isdigit():
            fields = line.split()
            if len(fields) == 4 and fields[0].isdigit() and fields[1].isdigit():
                vector_id, event, timestamp, value = fields
                if int(vector_id) in vector_ids:
                    values.append((int(event), float(timestamp), int(float(value))))
    return [value for _, _, value in sorted(values)]


if __name__ == "__main__":
    sys.exit(main())
