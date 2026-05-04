#!/usr/bin/env python3
"""
scenario-runner.py — Drives fake services through scripted incident phases.

Reads a scenario YAML and POSTs to fake service /control and /reset endpoints.
NthLayer detects and responds on its own — this script does NOT invoke NthLayer.

Usage:
    python demo/scenario-runner.py --scenario demo/scenario-cascading-failure.yaml [--base-url http://localhost]
"""

import argparse
import json
import signal
import sys
import time
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Union

try:
    import yaml
except ImportError:
    print("pyyaml is required: pip install pyyaml")
    sys.exit(1)

# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"

BLACK   = "\033[30m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
WHITE   = "\033[37m"

BG_BLACK  = "\033[40m"
BG_BLUE   = "\033[44m"

PHASE_COLOURS = [CYAN, YELLOW, MAGENTA, GREEN, BLUE]


def colour(text: str, *codes: str) -> str:
    return "".join(codes) + text + RESET


def header(text: str) -> str:
    bar = "─" * (len(text) + 4)
    return (
        f"\n{colour('┌' + bar + '┐', BOLD, CYAN)}\n"
        f"{colour('│  ' + text + '  │', BOLD, CYAN)}\n"
        f"{colour('└' + bar + '┘', BOLD, CYAN)}"
    )


def phase_banner(name: str, duration: int, index: int) -> str:
    c = PHASE_COLOURS[index % len(PHASE_COLOURS)]
    tag = colour(f" PHASE {index + 1} ", BOLD, BG_BLACK, c)
    label = colour(f" {name} ", BOLD, c)
    dur = colour(f"[{duration}s]", DIM)
    return f"\n{tag}{label}{dur}"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def post_json(url: str, payload: Optional[Dict] = None, timeout: int = 5) -> Optional[Dict]:
    body = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        print(colour(f"  HTTP {exc.code} from {url}", RED))
        return None
    except urllib.error.URLError as exc:
        print(colour(f"  Connection error for {url}: {exc.reason}", RED))
        return None


def control_service(base_url: str, port: int, control: Union[str, Dict]) -> None:
    """Send a control or reset action to a fake service."""
    if control == "reset":
        url = f"{base_url}:{port}/reset"
        result = post_json(url)
        status = colour("reset", GREEN) if result is not None else colour("reset (failed)", RED)
        print(f"  {colour('→', DIM)} :{port}/reset  {status}")
    elif isinstance(control, dict):
        url = f"{base_url}:{port}/control"
        result = post_json(url, control)
        params = "  ".join(f"{k}={v}" for k, v in control.items())
        status = colour("ok", GREEN) if result is not None else colour("failed", RED)
        print(f"  {colour('→', DIM)} :{port}/control  {colour(params, YELLOW)}  {status}")
    else:
        print(colour(f"  Unknown control value: {control!r}", RED))


# ---------------------------------------------------------------------------
# Countdown timer
# ---------------------------------------------------------------------------

def countdown(phase_name: str, duration: int) -> None:
    """Display an inline countdown that overwrites itself each second."""
    start = time.monotonic()
    try:
        for elapsed in range(duration):
            remaining = duration - elapsed
            bar_width = 30
            filled = int(bar_width * elapsed / duration)
            bar = colour("█" * filled, GREEN) + colour("░" * (bar_width - filled), DIM)
            line = (
                f"  {colour('▶', CYAN)} "
                f"{colour(phase_name, BOLD)} "
                f"[{bar}] "
                f"{colour(f'{elapsed + 1}s', YELLOW)}/{colour(f'{duration}s', DIM)}"
            )
            print(f"\r{line}", end="", flush=True)
            # Sleep until the next whole second relative to start
            target = start + elapsed + 1
            now = time.monotonic()
            if target > now:
                time.sleep(target - now)
        # Final tick
        bar = colour("█" * bar_width, GREEN)
        line = (
            f"  {colour('✓', GREEN)} "
            f"{colour(phase_name, BOLD)} "
            f"[{bar}] "
            f"{colour(f'{duration}s', GREEN)}/{colour(f'{duration}s', DIM)}"
        )
        print(f"\r{line}", flush=True)
    except KeyboardInterrupt:
        print()  # newline before re-raising
        raise


# ---------------------------------------------------------------------------
# Scenario execution
# ---------------------------------------------------------------------------

def load_scenario(path: str) -> dict:
    with open(path, "r") as fh:
        data = yaml.safe_load(fh)
    return data["scenario"]


def run_scenario(scenario: dict, base_url: str) -> None:
    services = scenario.get("services", {})
    phases = scenario.get("phases", [])

    print(header(scenario["name"]))
    if "description" in scenario:
        print(colour(scenario["description"].strip(), DIM))

    for i, phase in enumerate(phases):
        name = phase["name"]
        duration = int(phase.get("duration", 10))
        description = phase.get("description", "").strip()
        actions = phase.get("actions", [])

        print(phase_banner(name, duration, i))
        if description:
            print(colour(f"  {description}", DIM))

        for action in actions:
            svc_name = action["service"]
            control = action["control"]

            if svc_name not in services:
                print(colour(f"  Unknown service: {svc_name}", RED))
                continue

            port = services[svc_name]["port"]
            svc_label = colour(svc_name, BOLD)
            print(f"  {colour('service:', DIM)} {svc_label}")
            control_service(base_url, port, control)

        countdown(name, duration)

    print(colour("\nScenario complete.", BOLD, GREEN))


# ---------------------------------------------------------------------------
# Cleanup / signal handling
# ---------------------------------------------------------------------------

def reset_all_services(scenario: dict, base_url: str) -> None:
    services = scenario.get("services", {})
    if not services:
        return
    print(colour("\n  Resetting all services...", YELLOW))
    for svc_name, svc in services.items():
        port = svc["port"]
        url = f"{base_url}:{port}/reset"
        result = post_json(url)
        status = colour("reset", GREEN) if result is not None else colour("failed", RED)
        print(f"  {colour('→', DIM)} {svc_name} :{port}/reset  {status}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Drive fake services through a scripted incident scenario."
    )
    parser.add_argument(
        "--scenario",
        required=True,
        metavar="PATH",
        help="Path to the scenario YAML file.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost",
        metavar="URL",
        help="Base URL for fake services (default: http://localhost).",
    )
    args = parser.parse_args()

    try:
        scenario = load_scenario(args.scenario)
    except FileNotFoundError:
        print(colour(f"Scenario file not found: {args.scenario}", RED))
        sys.exit(1)
    except (yaml.YAMLError, KeyError) as exc:
        print(colour(f"Failed to parse scenario: {exc}", RED))
        sys.exit(1)

    # Register Ctrl+C handler after scenario is loaded
    def handle_interrupt(sig, frame):  # noqa: ANN001
        print(colour("\n\nInterrupted — resetting services before exit.", YELLOW))
        reset_all_services(scenario, args.base_url)
        print(colour("Done.", GREEN))
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_interrupt)

    run_scenario(scenario, args.base_url)


if __name__ == "__main__":
    main()
