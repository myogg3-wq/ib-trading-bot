from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.web.design_audit import build_design_audit, render_json, render_markdown


def maybe_capture_screenshot(url: str, output_path: Path) -> str | None:
    codex_home = Path.home() / ".codex"
    wrapper = codex_home / "skills" / "playwright" / "scripts" / "playwright_cli.sh"
    if not wrapper.exists():
        return None

    try:
        subprocess.run([str(wrapper), "kill-all"], check=False, capture_output=True, text=True)
        subprocess.run([str(wrapper), "open", url, "--headed"], check=True, capture_output=True, text=True)
        subprocess.run([str(wrapper), "screenshot"], check=True, capture_output=True, text=True)
    except Exception:
        return None

    latest_dir = Path.cwd() / ".playwright-cli"
    if not latest_dir.exists():
        return None
    screenshots = sorted(latest_dir.glob("page-*.png"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not screenshots:
        return None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    screenshots[0].replace(output_path)
    return str(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the design recursive improvement audit.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8766/platform?lang=ko")
    parser.add_argument(
        "--output-dir",
        default=str(Path("output") / "design-audit"),
        help="Directory for markdown/json outputs and optional screenshots.",
    )
    parser.add_argument("--skip-screenshot", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report = build_design_audit()

    if not args.skip_screenshot:
        screenshot_path = output_dir / "research-idle.png"
        captured = maybe_capture_screenshot(args.base_url, screenshot_path)
        if captured:
            report.artifacts["idle_screenshot"] = captured

    markdown_path = output_dir / "design_recursive_report.md"
    json_path = output_dir / "design_recursive_report.json"
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(render_json(report), encoding="utf-8")

    print(markdown_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
