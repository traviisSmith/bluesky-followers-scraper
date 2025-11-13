import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from extractors.bluesky_parser import BlueskyFollowerClient
from outputs.exporters import export_followers
from extractors.utils_time import sanitize_output_format

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("runner")

def load_settings(config_path: Path) -> Dict[str, Any]:
    """
    Load settings from the example configuration file.
    If loading fails, fall back to sensible defaults.
    """
    defaults: Dict[str, Any] = {
        "base_url": "https://public.api.bsky.app",
        "default_max_items": 100,
        "default_output_format": "json",
        "output_dir": "data",
        "http_timeout_seconds": 15,
    }

    if not config_path.is_file():
        logger.warning("Config file %s not found, using default settings.", config_path)
        return defaults

    try:
        with config_path.open("r", encoding="utf-8") as f:
            user_settings = json.load(f)
        if not isinstance(user_settings, dict):
            raise ValueError("Config root must be an object")
        merged = {**defaults, **user_settings}
        logger.info("Loaded settings from %s", config_path)
        return merged
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load config from %s: %s", config_path, exc)
        return defaults

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bluesky Followers Scraper - fetch followers for Bluesky profiles."
    )
    parser.add_argument(
        "-a",
        "--actor",
        help=(
            "Bluesky handle or DID to scrape followers for, e.g. "
            "'regeneratedarts.bsky.social' or 'did:plc:xyz'."
        ),
    )
    parser.add_argument(
        "-i",
        "--input-file",
        type=str,
        help=(
            "Optional path to a text file with one handle/DID per line. "
            "If provided, followers will be scraped for each non-empty line."
        ),
    )
    parser.add_argument(
        "-m",
        "--max-items",
        type=int,
        help="Maximum number of followers to fetch per actor (overrides config).",
    )
    parser.add_argument(
        "-f",
        "--format",
        dest="output_format",
        default=None,
        help="Output format: json, csv, xml, html, rss (overrides config).",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_path",
        default=None,
        help=(
            "Output file path. If omitted, data will be written to a default file "
            "in the configured output_dir, or to stdout for JSON."
        ),
    )
    parser.add_argument(
        "--config",
        dest="config_file",
        default=None,
        help="Optional path to a settings JSON file. Defaults to src/config/settings.example.json.",
    )
    return parser.parse_args()

def read_actors_from_file(path: Path) -> List[str]:
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    actors: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("#"):
                actors.append(cleaned)
    return actors

def ensure_output_path(
    base_dir: Path, output_path_arg: Optional[str], fmt: str, actor_tag: Optional[str]
) -> Optional[Path]:
    """
    Determine a concrete output path.

    If output_path_arg is provided:
        - If it ends with a directory separator or points to an existing directory,
          a filename is constructed inside it.
        - Otherwise, output_path_arg is treated as a full file path.
    If output_path_arg is None:
        - For JSON, None is returned to allow stdout usage.
        - For other formats, a file path inside base_dir is constructed.
    """
    if fmt == "json" and output_path_arg is None and actor_tag is None:
        # For single-actor JSON, allow stdout by returning None.
        return None

    tag = actor_tag or "followers"
    filename = f"bluesky_{tag}.{fmt}"

    if output_path_arg:
        candidate = Path(output_path_arg)
        if candidate.is_dir() or str(output_path_arg).endswith(("/", "\\")):
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate / filename
        # Ensure parent directory exists
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate

    # Default: data directory under repo
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / filename

def main() -> None:
    args = parse_args()

    # Resolve repository root as the parent of src/
    src_dir = Path(__file__).resolve().parent
    repo_root = src_dir.parent

    # Determine config file path
    if args.config_file:
        config_path = Path(args.config_file).resolve()
    else:
        config_path = src_dir / "config" / "settings.example.json"

    settings = load_settings(config_path)
    default_max = int(settings.get("default_max_items", 100))
    default_fmt = sanitize_output_format(
        settings.get("default_output_format", "json")
    ) or "json"
    output_dir = Path(settings.get("output_dir", "data"))
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir

    if not args.actor and not args.input_file:
        logger.error("You must provide either --actor or --input-file.")
        sys.exit(1)

    actors: List[str] = []
    if args.actor:
        actors.append(args.actor.strip())

    if args.input_file:
        input_path = Path(args.input_file).resolve()
        try:
            file_actors = read_actors_from_file(input_path)
            actors.extend(file_actors)
        except FileNotFoundError as exc:
            logger.error(str(exc))
            sys.exit(1)

    if not actors:
        logger.error("No valid actors provided in arguments or input file.")
        sys.exit(1)

    max_items = args.max_items if args.max_items and args.max_items > 0 else default_max
    fmt = sanitize_output_format(args.output_format) or default_fmt

    client = BlueskyFollowerClient(
        base_url=settings.get("base_url", "https://public.api.bsky.app"),
        timeout_seconds=int(settings.get("http_timeout_seconds", 15)),
    )

    all_results: Dict[str, List[Dict[str, Any]]] = {}
    for actor in actors:
        logger.info("Fetching followers for actor '%s' (max_items=%d)...", actor, max_items)
        try:
            followers = client.fetch_followers(actor=actor, limit=max_items)
            all_results[actor] = followers
            logger.info("Fetched %d followers for '%s'.", len(followers), actor)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch followers for '%s': %s", actor, exc, exc_info=True)

    # If multiple actors are requested, combine and add actor field
    combined: List[Dict[str, Any]] = []
    for actor, followers in all_results.items():
        for follower in followers:
            if "source_actor" not in follower:
                follower["source_actor"] = actor
            combined.append(follower)

    if not combined:
        logger.warning("No followers were retrieved for any actor.")
        sys.exit(0)

    is_multi_actor = len(actors) > 1
    actor_tag = "multi" if is_multi_actor else actors[0].replace(":", "_").replace("/", "_")

    output_path = ensure_output_path(
        base_dir=output_dir,
        output_path_arg=args.output_path,
        fmt=fmt,
        actor_tag=actor_tag,
    )

    logger.info(
        "Exporting %d follower records in '%s' format to %s",
        len(combined),
        fmt,
        str(output_path) if output_path else "stdout",
    )

    try:
        export_followers(combined, fmt=fmt, output_path=output_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to export followers: %s", exc, exc_info=True)
        sys.exit(1)

    logger.info("Done.")

if __name__ == "__main__":
    main()