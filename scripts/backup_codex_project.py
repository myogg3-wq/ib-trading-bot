#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import secrets
import signal
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Seoul")
PROJECT_NAME = "ib-trading-bot"
PROJECT_SOURCE = Path("/Users/sehee/Desktop/SUB_Factory/Auto_Cash/ib-trading-bot")
GOOGLE_DRIVE_ACCOUNT_ROOT = Path.home() / "Library" / "CloudStorage" / "GoogleDrive-marine.wave4@gmail.com"
BACKUP_FACTORY_NAME = "FACTORY[NO DELETE]"
BACKUP_ROOT_NAME = "Auto_Investing"
LOCAL_SECRET_ROOT = Path.home() / ".codex-backup-secrets"
RECOVERY_KEY_FILE = LOCAL_SECRET_ROOT / f"{PROJECT_NAME}.recovery-key"
CODEx_PROFILE_ROOT = Path.home() / ".codex"
CODEx_PROFILE_INCLUDE = [
    "config.toml",
    "AGENTS.md",
    "skills",
    "automations",
    "memories",
]
LAUNCHD_LABEL = "com.sehee.codex.backup.ib-trading-bot"
LAUNCHD_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
LAUNCHD_LOG_PATH = Path.home() / "Library" / "Logs" / "codex-backup-ib-trading-bot.log"
PYTHON_EXECUTABLE = Path("/Users/sehee/.homebrew/bin/python3") if Path("/Users/sehee/.homebrew/bin/python3").exists() else Path(sys.executable)
SCRIPT_PATH = Path(__file__).resolve()
RESTORE_SCRIPT_PATH = SCRIPT_PATH.parent / "restore_codex_project.py"
EXCLUDE_FILE = SCRIPT_PATH.parent / "backup_excludes.txt"
BOOTSTRAP_DIRNAME = "bootstrap"
RETENTION_DAYS = 180
CLOUD_WRITE_TIMEOUT_SECONDS = 30


class BackupError(RuntimeError):
    pass


@dataclass
class BackupContext:
    factory_root: Path
    backup_root: Path
    project_root: Path
    global_root: Path
    bootstrap_root: Path


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=check,
    )


def run_shell(command: str, *, cwd: Path | None = None) -> None:
    subprocess.run(
        ["/bin/zsh", "-lc", command],
        cwd=str(cwd) if cwd else None,
        check=True,
    )


def sha256_file(path: Path) -> str:
    if "CloudStorage" in path.parts:
        return "not-computed-cloudstorage"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def is_cloud_path(path: Path) -> bool:
    return "CloudStorage" in path.parts


def write_text_file(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not is_cloud_path(path):
        path.write_text(body, encoding="utf-8")
        return

    LOCAL_SECRET_ROOT.mkdir(parents=True, exist_ok=True)
    local_tmp = LOCAL_SECRET_ROOT / f"{path.name}.{os.getpid()}.tmp"
    local_tmp.write_text(body, encoding="utf-8")
    try:
        subprocess.run(["/bin/cp", str(local_tmp), str(path)], check=True, timeout=CLOUD_WRITE_TIMEOUT_SECONDS)
    finally:
        local_tmp.unlink(missing_ok=True)


def write_json(path: Path, payload: dict) -> None:
    body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    try:
        write_text_file(path, body)
    except (OSError, subprocess.SubprocessError) as exc:
        if "latest" not in path.name:
            raise
        print(f"warning: could not update {path.name}: {exc}", file=sys.stderr)


def normalized_name(path: Path) -> str:
    return path.name


def discover_factory_root() -> Path:
    if not GOOGLE_DRIVE_ACCOUNT_ROOT.exists():
        raise BackupError(f"Google Drive account root not found: {GOOGLE_DRIVE_ACCOUNT_ROOT}")

    for top_level in GOOGLE_DRIVE_ACCOUNT_ROOT.iterdir():
        if top_level.name.startswith(".") or not top_level.is_dir():
            continue
        direct = top_level / BACKUP_FACTORY_NAME
        if direct.exists():
            return direct
        try:
            for child in top_level.iterdir():
                if child.name == BACKUP_FACTORY_NAME and child.is_dir():
                    return child
        except PermissionError:
            continue
    raise BackupError(f"{BACKUP_FACTORY_NAME} not found under Google Drive root")


def build_context() -> BackupContext:
    factory_root = discover_factory_root()
    backup_root = factory_root / BACKUP_ROOT_NAME
    project_root = backup_root / "projects" / PROJECT_NAME
    global_root = backup_root / "_global" / "codex-profile"
    bootstrap_root = backup_root / "_global" / BOOTSTRAP_DIRNAME

    for base in [
        project_root / "docs",
        project_root / "env",
        project_root / "git",
        project_root / "manifests",
        project_root / "ops" / "launchd",
        project_root / "snapshots" / "full",
        project_root / "snapshots" / "latest",
        global_root / "docs",
        global_root / "manifests",
        global_root / "snapshots" / "full",
        bootstrap_root / "tools" / PROJECT_NAME,
    ]:
        base.mkdir(parents=True, exist_ok=True)

    return BackupContext(
        factory_root=factory_root,
        backup_root=backup_root,
        project_root=project_root,
        global_root=global_root,
        bootstrap_root=bootstrap_root,
    )


def ensure_recovery_key() -> Path:
    LOCAL_SECRET_ROOT.mkdir(parents=True, exist_ok=True)
    if not RECOVERY_KEY_FILE.exists():
        RECOVERY_KEY_FILE.write_text(base64.urlsafe_b64encode(secrets.token_bytes(48)).decode("ascii") + "\n", encoding="utf-8")
        os.chmod(RECOVERY_KEY_FILE, 0o600)
    else:
        os.chmod(RECOVERY_KEY_FILE, 0o600)
    return RECOVERY_KEY_FILE


def _alarm_timeout(_signum: int, _frame: object) -> None:
    raise TimeoutError("timed out while reading Google Drive metadata")


def load_json_if_exists(path: Path, *, timeout_seconds: int = 3) -> dict | None:
    if not path.exists():
        return None
    previous_handler = signal.signal(signal.SIGALRM, _alarm_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TimeoutError, json.JSONDecodeError):
        return None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def git_value(args: Iterable[str]) -> str:
    return run(["git", *args], cwd=PROJECT_SOURCE).stdout.strip()


def project_fingerprint() -> tuple[str, dict]:
    branch = git_value(["rev-parse", "--abbrev-ref", "HEAD"])
    commit = git_value(["rev-parse", "HEAD"])
    status = git_value(["status", "--short", "--untracked-files=all"])
    tracked = git_value(["ls-files"])

    env_parts: list[str] = []
    for rel in [".env", ".env.local", ".env.production", ".claude/settings.local.json"]:
        candidate = PROJECT_SOURCE / rel
        if candidate.exists():
            stat = candidate.stat()
            env_parts.append(f"{rel}:{stat.st_size}:{int(stat.st_mtime)}")

    raw = "\n".join([branch, commit, status, tracked, *env_parts])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    status_lines = [line for line in status.splitlines() if line.strip()]
    metadata = {
        "branch": branch,
        "commit": commit,
        "status_line_count": len(status_lines),
        "status_preview": status_lines[:50],
    }
    return digest, metadata


def codex_fingerprint() -> str:
    parts: list[str] = []
    for rel in CODEx_PROFILE_INCLUDE:
        candidate = CODEx_PROFILE_ROOT / rel
        if not candidate.exists():
            continue
        if candidate.is_file():
            stat = candidate.stat()
            parts.append(f"{rel}:{stat.st_size}:{int(stat.st_mtime)}")
        else:
            for item in sorted(candidate.rglob("*")):
                if not item.is_file():
                    continue
                stat = item.stat()
                parts.append(f"{item.relative_to(CODEx_PROFILE_ROOT)}:{stat.st_size}:{int(stat.st_mtime)}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def timestamp_now() -> tuple[str, str, str]:
    now = datetime.now(TZ)
    stamp = now.strftime("%Y%m%dT%H%M%S")
    year = now.strftime("%Y")
    month = now.strftime("%m")
    day = now.strftime("%d")
    return stamp, year, month, day


def create_git_bundle(path: Path) -> None:
    run(["git", "bundle", "create", str(path), "--all"], cwd=PROJECT_SOURCE)


def create_full_snapshot(destination: Path) -> None:
    exclude = f"--exclude-from={shlex_quote(str(EXCLUDE_FILE))}"
    command = (
        f"tar -C {shlex_quote(str(PROJECT_SOURCE))} {exclude} -cf - . "
        f"| {shlex_quote(str(shutil.which('zstd') or 'zstd'))} -T0 -19 -o {shlex_quote(str(destination))}"
    )
    run_shell(command)


def create_encrypted_project_env(destination: Path, key_file: Path) -> list[str]:
    candidates = [".env", ".env.local", ".env.production", ".claude/settings.local.json"]
    existing = [rel for rel in candidates if (PROJECT_SOURCE / rel).exists()]
    if not existing:
        return []

    joined = " ".join(shlex_quote(rel) for rel in existing)
    zstd_bin = shutil.which("zstd") or "zstd"
    openssl_bin = shutil.which("openssl") or "openssl"
    command = (
        f"tar -C {shlex_quote(str(PROJECT_SOURCE))} -cf - {joined} "
        f"| {shlex_quote(zstd_bin)} -T0 -19 "
        f"| {shlex_quote(openssl_bin)} enc -aes-256-cbc -pbkdf2 -iter 200000 -salt "
        f"-out {shlex_quote(str(destination))} -pass file:{shlex_quote(str(key_file))}"
    )
    run_shell(command)
    return existing


def create_codex_profile_snapshot(destination: Path) -> list[str]:
    existing = [rel for rel in CODEx_PROFILE_INCLUDE if (CODEx_PROFILE_ROOT / rel).exists()]
    if not existing:
        return []
    joined = " ".join(shlex_quote(rel) for rel in existing)
    zstd_bin = shutil.which("zstd") or "zstd"
    command = (
        f"tar -C {shlex_quote(str(CODEx_PROFILE_ROOT))} -cf - {joined} "
        f"| {shlex_quote(zstd_bin)} -T0 -19 -o {shlex_quote(str(destination))}"
    )
    run_shell(command)
    return existing


def copy_if_exists(source: Path, dest: Path) -> None:
    if source.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        if is_cloud_path(dest):
            try:
                subprocess.run(["/bin/cp", "-p", str(source), str(dest)], check=True, timeout=CLOUD_WRITE_TIMEOUT_SECONDS)
            except subprocess.SubprocessError as exc:
                print(f"warning: could not copy {source.name}: {exc}", file=sys.stderr)
        else:
            shutil.copy2(source, dest)


def write_restore_docs(ctx: BackupContext, manifest: dict) -> None:
    docs_root = ctx.project_root / "docs"
    restore_doc = docs_root / "RESTORE.md"
    write_text_file(
        restore_doc,
        f"""# {PROJECT_NAME} Restore Guide

## Quick restore
1. Open Google Drive folder: `{ctx.project_root}`
2. Copy the project backup scripts from `{ctx.bootstrap_root / 'tools' / PROJECT_NAME}`
3. On the new machine, place the recovery key file at `{RECOVERY_KEY_FILE}`
4. Run:

```bash
python3 restore_codex_project.py --project-name {PROJECT_NAME} --target ~/Desktop/{PROJECT_NAME}
```

## Included backup artifacts
- Full worktree snapshot: `{manifest['artifacts']['full_snapshot']['relative_path']}`
- Git bundle: `{manifest['artifacts']['git_bundle']['relative_path']}`
- Encrypted env archive: `{manifest['artifacts']['encrypted_env']['relative_path'] if manifest['artifacts']['encrypted_env'] else 'not present'}`
- Codex profile snapshot: `{manifest['codex_profile_artifact']['relative_path'] if manifest.get('codex_profile_artifact') else 'not updated in this run'}`

## Recovery key
- Local path on this machine: `{RECOVERY_KEY_FILE}`
- This key is not stored in Google Drive. Save it to a password manager or offline vault.

## Recommended next steps after restore
1. Review `{docs_root / 'CURRENT_STATUS.latest.md'}`
2. Review `{docs_root / 'TRANSFER_TO_NEW_MACHINE.latest.md'}`
3. Restore `.env` using the encrypted env archive
4. Start the stack with:

```bash
cd ~/Desktop/{PROJECT_NAME}
docker compose up -d --build
```
""",
    )

    copy_if_exists(PROJECT_SOURCE / "CURRENT_STATUS.md", docs_root / "CURRENT_STATUS.latest.md")
    copy_if_exists(PROJECT_SOURCE / "TRANSFER_TO_NEW_MACHINE.md", docs_root / "TRANSFER_TO_NEW_MACHINE.latest.md")
    copy_if_exists(PROJECT_SOURCE / ".env.example", docs_root / "env.example.latest")


def write_global_docs(ctx: BackupContext, codex_manifest: dict) -> None:
    docs_root = ctx.global_root / "docs"
    docs_root.mkdir(parents=True, exist_ok=True)
    write_text_file(
        docs_root / "RESTORE_CODEX_PROFILE.md",
        f"""# Codex profile restore

1. Locate the latest Codex profile snapshot in `{ctx.global_root / 'snapshots' / 'full'}`
2. Extract it into a temporary directory:

```bash
zstd -dc /path/to/codex-profile.tar.zst | tar -xf - -C /tmp/codex-profile-restore
```

3. Copy the needed folders into `~/.codex`

Included directories:
{os.linesep.join(f"- {item}" for item in codex_manifest.get('included_paths', []))}
""",
    )


def collect_ops_info(ctx: BackupContext, manifest: dict) -> None:
    ops_root = ctx.project_root / "ops"
    host_info = {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": sys.version,
        "project_source": str(PROJECT_SOURCE),
        "backup_script": str(SCRIPT_PATH),
        "restore_script": str(RESTORE_SCRIPT_PATH),
        "launchd_label": LAUNCHD_LABEL,
    }
    write_json(ops_root / "host-info.latest.json", host_info)
    write_json(ops_root / "latest-manifest-summary.json", manifest)
    copy_if_exists(LAUNCHD_PLIST_PATH, ops_root / "launchd" / LAUNCHD_PLIST_PATH.name)


def relative_to_backup_root(path: Path, backup_root: Path) -> str:
    return str(path.relative_to(backup_root))


def shlex_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)


def prune_old_files(root: Path) -> None:
    if "CloudStorage" in root.parts:
        return
    cutoff = datetime.now(TZ).timestamp() - (RETENTION_DAYS * 86400)
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        if item.stat().st_mtime < cutoff:
            item.unlink()


def write_launchd_plist() -> None:
    LAUNCHD_PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LAUNCHD_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{PYTHON_EXECUTABLE}</string>
    <string>{SCRIPT_PATH}</string>
    <string>run</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{PROJECT_SOURCE}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>3600</integer>
  <key>StandardOutPath</key>
  <string>{LAUNCHD_LOG_PATH}</string>
  <key>StandardErrorPath</key>
  <string>{LAUNCHD_LOG_PATH}</string>
</dict>
</plist>
"""
    LAUNCHD_PLIST_PATH.write_text(plist, encoding="utf-8")


def install_launchd() -> None:
    write_launchd_plist()
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(LAUNCHD_PLIST_PATH)], check=False)
    run(["launchctl", "bootstrap", f"gui/{uid}", str(LAUNCHD_PLIST_PATH)])
    run(["launchctl", "enable", f"gui/{uid}/{LAUNCHD_LABEL}"])
    run(["launchctl", "kickstart", "-k", f"gui/{uid}/{LAUNCHD_LABEL}"])


def backup_once() -> dict:
    if not PROJECT_SOURCE.exists():
        raise BackupError(f"Project source not found: {PROJECT_SOURCE}")
    if not EXCLUDE_FILE.exists():
        raise BackupError(f"Exclude file not found: {EXCLUDE_FILE}")

    ctx = build_context()
    key_file = ensure_recovery_key()
    stamp, year, month, day = timestamp_now()

    project_manifest_path = ctx.project_root / "manifests" / "latest.json"
    previous_project_manifest = load_json_if_exists(project_manifest_path)
    current_fingerprint, git_meta = project_fingerprint()
    project_changed = previous_project_manifest is None or previous_project_manifest.get("fingerprint") != current_fingerprint

    codex_manifest_path = ctx.global_root / "manifests" / "latest.json"
    previous_codex_manifest = load_json_if_exists(codex_manifest_path)
    current_codex_fingerprint = codex_fingerprint()
    codex_changed = previous_codex_manifest is None or previous_codex_manifest.get("fingerprint") != current_codex_fingerprint

    result: dict = {
        "project_changed": project_changed,
        "codex_changed": codex_changed,
        "project_manifest": previous_project_manifest,
        "codex_manifest": previous_codex_manifest,
        "context": {
            "backup_root": str(ctx.backup_root),
            "project_root": str(ctx.project_root),
            "global_root": str(ctx.global_root),
            "recovery_key_file": str(key_file),
        },
    }

    if project_changed:
        full_dir = ctx.project_root / "snapshots" / "full" / year / month / day
        full_dir.mkdir(parents=True, exist_ok=True)
        full_snapshot = full_dir / f"{PROJECT_NAME}-{stamp}-worktree.tar.zst"
        git_bundle = ctx.project_root / "git" / f"{PROJECT_NAME}-{stamp}.bundle"
        env_archive = ctx.project_root / "env" / f"{PROJECT_NAME}-{stamp}-env.tar.zst.enc"

        create_full_snapshot(full_snapshot)
        create_git_bundle(git_bundle)
        encrypted_items = create_encrypted_project_env(env_archive, key_file)
        if not encrypted_items:
            env_archive.unlink(missing_ok=True)

        manifest = {
            "project_name": PROJECT_NAME,
            "created_at": datetime.now(TZ).isoformat(),
            "source_path": str(PROJECT_SOURCE),
            "backup_root": str(ctx.project_root),
            "fingerprint": current_fingerprint,
            "git": git_meta,
            "artifacts": {
                "full_snapshot": {
                    "path": str(full_snapshot),
                    "relative_path": relative_to_backup_root(full_snapshot, ctx.backup_root),
                    "sha256": sha256_file(full_snapshot),
                    "size_bytes": file_size(full_snapshot),
                },
                "git_bundle": {
                    "path": str(git_bundle),
                    "relative_path": relative_to_backup_root(git_bundle, ctx.backup_root),
                    "sha256": sha256_file(git_bundle),
                    "size_bytes": file_size(git_bundle),
                },
                "encrypted_env": (
                    {
                        "path": str(env_archive),
                        "relative_path": relative_to_backup_root(env_archive, ctx.backup_root),
                        "sha256": sha256_file(env_archive),
                        "size_bytes": file_size(env_archive),
                        "included_paths": encrypted_items,
                    }
                    if encrypted_items
                    else None
                ),
            },
            "restore": {
                "restore_script": relative_to_backup_root(ctx.bootstrap_root / "tools" / PROJECT_NAME / RESTORE_SCRIPT_PATH.name, ctx.backup_root),
                "launchd_plist": str(LAUNCHD_PLIST_PATH),
            },
        }

        timestamp_manifest = ctx.project_root / "manifests" / f"manifest-{stamp}.json"
        write_json(timestamp_manifest, manifest)
        write_json(project_manifest_path, manifest)
        write_restore_docs(ctx, manifest)
        collect_ops_info(ctx, manifest)
        result["project_manifest"] = manifest

    if codex_changed:
        full_dir = ctx.global_root / "snapshots" / "full" / year / month / day
        full_dir.mkdir(parents=True, exist_ok=True)
        codex_snapshot = full_dir / f"codex-profile-{stamp}.tar.zst"
        included_paths = create_codex_profile_snapshot(codex_snapshot)
        codex_manifest = {
            "created_at": datetime.now(TZ).isoformat(),
            "fingerprint": current_codex_fingerprint,
            "included_paths": included_paths,
            "artifact": {
                "path": str(codex_snapshot),
                "relative_path": relative_to_backup_root(codex_snapshot, ctx.backup_root),
                "sha256": sha256_file(codex_snapshot),
                "size_bytes": file_size(codex_snapshot),
            },
        }
        write_json(ctx.global_root / "manifests" / f"manifest-{stamp}.json", codex_manifest)
        write_json(codex_manifest_path, codex_manifest)
        write_global_docs(ctx, codex_manifest)
        result["codex_manifest"] = codex_manifest
        if result.get("project_manifest") is not None:
            result["project_manifest"]["codex_profile_artifact"] = codex_manifest["artifact"]
            write_json(project_manifest_path, result["project_manifest"])
            write_restore_docs(ctx, result["project_manifest"])

    bootstrap_target = ctx.bootstrap_root / "tools" / PROJECT_NAME
    for tool in [SCRIPT_PATH, RESTORE_SCRIPT_PATH, EXCLUDE_FILE]:
        copy_if_exists(tool, bootstrap_target / tool.name)
    write_json(
        ctx.bootstrap_root / "backup-index.latest.json",
        {
            "updated_at": datetime.now(TZ).isoformat(),
            "project_name": PROJECT_NAME,
            "project_manifest": str(ctx.project_root / "manifests" / "latest.json"),
            "codex_manifest": str(ctx.global_root / "manifests" / "latest.json"),
            "recovery_key_note": f"Stored locally at {RECOVERY_KEY_FILE}. Save this key outside Google Drive.",
        },
    )

    prune_old_files(ctx.project_root / "snapshots")
    prune_old_files(ctx.project_root / "git")
    prune_old_files(ctx.project_root / "env")
    prune_old_files(ctx.global_root / "snapshots")

    return result


def status() -> None:
    ctx = build_context()
    payload = {
        "project_manifest": load_json_if_exists(ctx.project_root / "manifests" / "latest.json"),
        "codex_manifest": load_json_if_exists(ctx.global_root / "manifests" / "latest.json"),
        "launchd_loaded": subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"],
            text=True,
            capture_output=True,
        ).returncode
        == 0,
        "launchd_plist": str(LAUNCHD_PLIST_PATH),
        "backup_root": str(ctx.backup_root),
        "recovery_key_file": str(RECOVERY_KEY_FILE),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup ib-trading-bot to Google Drive.")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "install-launchd", "status"])
    args = parser.parse_args()

    if args.command == "run":
        result = backup_once()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    if args.command == "install-launchd":
        install_launchd()
        print(json.dumps({"installed": True, "plist": str(LAUNCHD_PLIST_PATH)}, ensure_ascii=False))
        return
    if args.command == "status":
        status()
        return


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        print(f"backup_codex_project.py failed: {exc}", file=sys.stderr)
        raise
