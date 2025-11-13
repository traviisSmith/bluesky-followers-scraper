import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree as ET

from extractors.utils_time import sanitize_output_format

logger = logging.getLogger("exporters")

def _ensure_parent_dir(path: Path) -> None:
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

def _to_serializable(value: Any) -> Any:
    """
    Ensure the value is JSON serializable. Complex structures are left as-is for JSON,
    but this helper is used for CSV and similar formats to stringify nested data.
    """
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)

def _write_json(followers: List[Dict[str, Any]], output_path: Optional[Path]) -> None:
    if output_path is None:
        # Write to stdout
        print(json.dumps(followers, ensure_ascii=False, indent=2))
        return

    _ensure_parent_dir(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(followers, f, ensure_ascii=False, indent=2)

def _write_csv(followers: List[Dict[str, Any]], output_path: Path) -> None:
    _ensure_parent_dir(output_path)

    # Collect all keys so we don't lose any fields
    fieldnames: List[str] = []
    for follower in followers:
        for key in follower.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for follower in followers:
            row = {k: _to_serializable(v) for k, v in follower.items()}
            writer.writerow(row)

def _write_xml(followers: List[Dict[str, Any]], output_path: Path) -> None:
    _ensure_parent_dir(output_path)

    root = ET.Element("followers")
    for follower in followers:
        node = ET.SubElement(root, "follower")
        for key, value in follower.items():
            child = ET.SubElement(node, key)
            if isinstance(value, (dict, list)):
                child.text = json.dumps(value, ensure_ascii=False)
            elif value is None:
                child.text = ""
            else:
                child.text = str(value)

    tree = ET.ElementTree(root)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

def _write_html(followers: List[Dict[str, Any]], output_path: Path) -> None:
    _ensure_parent_dir(output_path)

    if not followers:
        html_body = "<p>No followers to display.</p>"
        keys: Iterable[str] = []
    else:
        keys = followers[0].keys()
        rows = []
        for follower in followers:
            cells = "".join(
                f"<td>{_escape_html(_to_serializable(follower.get(k, '')))}</td>"
                for k in keys
            )
            rows.append(f"<tr>{cells}</tr>")
        header_cells = "".join(f"<th>{_escape_html(k)}</th>" for k in keys)
        html_body = (
            "<table border='1' cellspacing='0' cellpadding='4'>"
            f"<thead><tr>{header_cells}</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Bluesky Followers Export</title>
    <style>
        body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ padding: 6px 8px; text-align: left; }}
        thead {{ background-color: #f1f1f1; }}
        tr:nth-child(even) {{ background-color: #fafafa; }}
    </style>
</head>
<body>
<h1>Bluesky Followers Export</h1>
{html_body}
</body>
</html>
"""

    with output_path.open("w", encoding="utf-8") as f:
        f.write(html)

def _escape_html(value: Any) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

def _write_rss(followers: List[Dict[str, Any]], output_path: Path) -> None:
    _ensure_parent_dir(output_path)

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    title = ET.SubElement(channel, "title")
    title.text = "Bluesky Followers Scraper Feed"

    description = ET.SubElement(channel, "description")
    description.text = (
        "Feed generated from Bluesky followers data for analytics and monitoring."
    )

    link = ET.SubElement(channel, "link")
    link.text = "https://bsky.app/"

    for follower in followers:
        item = ET.SubElement(channel, "item")
        title_node = ET.SubElement(item, "title")
        display_name = follower.get("displayName") or follower.get("handle") or "Unknown"
        title_node.text = str(display_name)

        link_node = ET.SubElement(item, "link")
        link_node.text = str(follower.get("link_to_profile") or "")

        guid_node = ET.SubElement(item, "guid")
        guid_node.text = str(follower.get("did") or follower.get("handle") or "")

        desc_node = ET.SubElement(item, "description")
        desc = follower.get("description") or ""
        desc_node.text = desc

    tree = ET.ElementTree(rss)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

def export_followers(
    followers: List[Dict[str, Any]],
    fmt: str,
    output_path: Optional[Path] = None,
) -> None:
    """
    Export follower data to the desired format.

    :param followers: List of follower records.
    :param fmt: Output format: json, csv, xml, html, rss.
    :param output_path: Where to write the output. If None and fmt == 'json', stdout is used.
    """
    if not followers:
        logger.warning("No followers to export.")
        if fmt == "json" and output_path is None:
            print("[]")
        return

    normalized_fmt = sanitize_output_format(fmt)
    if not normalized_fmt:
        raise ValueError(f"Unknown or empty output format: {fmt}")

    if normalized_fmt == "json":
        _write_json(followers, output_path)
    elif normalized_fmt == "csv":
        if output_path is None:
            raise ValueError("CSV export requires a file path.")
        _write_csv(followers, output_path)
    elif normalized_fmt == "xml":
        if output_path is None:
            raise ValueError("XML export requires a file path.")
        _write_xml(followers, output_path)
    elif normalized_fmt == "html":
        if output_path is None:
            raise ValueError("HTML export requires a file path.")
        _write_html(followers, output_path)
    elif normalized_fmt == "rss":
        if output_path is None:
            raise ValueError("RSS export requires a file path.")
        _write_rss(followers, output_path)
    else:
        raise ValueError(f"Unsupported output format: {fmt}")