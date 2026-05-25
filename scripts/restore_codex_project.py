#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_NAME = "ib-trading-bot"
GOOGLE_DRIVE_ACCOUNT_ROOT = Path.home() / "Library" / "CloudStorage" / "GoogleDrive-marine.wave4@gmail.com"
BACKUP_FACTORY_NAME = "FACTORY[NO DELETE]"
BACKUP_ROOT_NAME = "Auto_Investing"
DEFAULT_KEY_FILE = Path.home() / ".codex-backup-secrets" / f"{PROJECT_NAME}.recovery-key"


class RestoreError(RuntimeError):
    pass


def discover_factory_root() -> Path:
    if not GOOGLE_DRIVE_ACCOUNT_ROOT.exists():
        raise RestoreError(f"Google Drive root not found: {GOOGLE_DRIVE_ACCOUNT_ROOT}")
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
    raise RestoreError(f"{BACKUP_FACTORY_NAME} not found")


def backup_root() -> Path:
    return discover_factory_root() / BACKUP_ROOT_NAME


def load_latest_manifest(project_name: str) -> dict:
    manifest_path = backup_root() / "projects" / project_name / "manifests" / "latest.json"
    if not manifest_path.exists():
        raise RestoreError(f"Latest manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def extract_zstd_tar(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    zstd_bin = shutil.which("zstd") or "zstd"
    with subprocess.Popen([zstd_bin, "-dc", str(archive)], stdout=subprocess.PIPE) as zstd_proc:
        subprocess.run(["tar", "-xf", "-", "-C", str(target)], stdin=zstd_proc.stdout, check=True)
        if zstd_proc.stdout:
            zstd_proc.stdout.close()
        rc = zstd_proc.wait()
        if rc != 0:
            raise RestoreError(f"zstd failed for archive: {archive}")


def decrypt_and_extract(archive: Path, target: Path, key_file: Path) -> None:
    if not key_file.exists():
        raise RestoreError(f"Recovery key file not found: {key_file}")
    target.mkdir(parents=True, exist_ok=True)
    openssl_bin = shutil.which("openssl") or "openssl"
    zstd_bin = shutil.which("zstd") or "zstd"

    with subprocess.Popen(
        [
            openssl_bin,
            "enc",
            "-d",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            "200000",
            "-in",
            str(archive),
            "-pass",
            f"file:{key_file}",
        ],
        stdout=subprocess.PIPE,
    ) as openssl_proc:
        with subprocess.Popen([zstd_bin, "-dc"], stdin=openssl_proc.stdout, stdout=subprocess.PIPE) as zstd_proc:
            subprocess.run(["tar", "-xf", "-", "-C", str(target)], stdin=zstd_proc.stdout, check=True)
            if openssl_proc.stdout:
                openssl_proc.stdout.close()
            if zstd_proc.stdout:
                zstd_proc.stdout.close()
            zstd_rc = zstd_proc.wait()
            openssl_rc = openssl_proc.wait()
            if zstd_rc != 0 or openssl_rc != 0:
                raise RestoreError(f"Failed to decrypt and extract env archive: {archive}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore ib-trading-bot from Google Drive backup.")
    parser.add_argument("--project-name", default=PROJECT_NAME)
    parser.add_argument("--target", required=True, help="Directory to restore the project into")
    parser.add_argument("--key-file", default=str(DEFAULT_KEY_FILE))
    parser.add_argument("--skip-env", action="store_true")
    args = parser.parse_args()

    manifest = load_latest_manifest(args.project_name)
    target = Path(args.target).expanduser().resolve()
    key_file = Path(args.key_file).expanduser().resolve()

    full_snapshot = Path(manifest["artifacts"]["full_snapshot"]["path"])
    extract_zstd_tar(full_snapshot, target)

    env_artifact = manifest["artifacts"].get("encrypted_env")
    if env_artifact and not args.skip_env:
        decrypt_and_extract(Path(env_artifact["path"]), target, key_file)

    print(
        json.dumps(
            {
                "restored_to": str(target),
                "full_snapshot": str(full_snapshot),
                "env_restored": bool(env_artifact and not args.skip_env),
                "next_step": f"cd {target} && docker compose up -d --build",
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"restore_codex_project.py failed: {exc}", file=sys.stderr)
        raise
