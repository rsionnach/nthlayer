from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from nthlayer.providers.lock import DEFAULT_LOCK_PATH, load_lock, save_lock
from nthlayer.providers.registry import list_providers


def _format_provider_info(name: str, version: str | None, description: str | None) -> str:
    version_display = version or "unknown"
    if description:
        return f"{name}\t{version_display}\t{description}"
    return f"{name}\t{version_display}"


def _resolve_lock_path(value: str | None) -> Path:
    return Path(value).expanduser() if value else DEFAULT_LOCK_PATH


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nthlayer.providers", description="NthLayer provider tooling")
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="List available providers")
    list_parser.add_argument("--lockfile", help="Path to provider lockfile", default=None)

    info_parser = subparsers.add_parser("info", help="Show provider details")
    info_parser.add_argument("name", help="Provider name")

    install_parser = subparsers.add_parser("install", help="Record provider version in the lockfile")
    install_parser.add_argument("name", help="Provider name")
    install_parser.add_argument("--lockfile", help="Path to provider lockfile", default=None)

    update_parser = subparsers.add_parser("update", help="Update provider version in the lockfile")
    update_parser.add_argument("name", help="Provider name")
    update_parser.add_argument("--lockfile", help="Path to provider lockfile", default=None)

    args = parser.parse_args(argv)

    if args.command == "list":
        lock = load_lock(_resolve_lock_path(args.lockfile))
        for spec in list_providers():
            locked_version = lock.get(spec.name)
            display_version = locked_version or spec.version
            print(_format_provider_info(spec.name, display_version, spec.description))
        return 0

    if args.command == "info":
        providers = {spec.name: spec for spec in list_providers()}
        if args.name not in providers:
            parser.error(f"Provider '{args.name}' is not registered")
        spec = providers[args.name]
        print(f"Name: {spec.name}")
        print(f"Version: {spec.version or 'unknown'}")
        if spec.description:
            print(f"Description: {spec.description}")
        else:
            print("Description: (not provided)")
        return 0

    if args.command in {"install", "update"}:
        providers = {spec.name: spec for spec in list_providers()}
        if args.name not in providers:
            parser.error(f"Provider '{args.name}' is not registered")
        lock_path = _resolve_lock_path(args.lockfile)
        lock = load_lock(lock_path)
        spec = providers[args.name]
        lock.set(args.name, spec.version or "unknown")
        save_lock(lock, lock_path)
        action = "Installed" if args.command == "install" else "Updated"
        print(f"{action} provider '{args.name}' (version: {spec.version or 'unknown'}) in {lock_path}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover - exercised via module entrypoint
    raise SystemExit(main())
