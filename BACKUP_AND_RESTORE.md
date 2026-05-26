# Backup And Restore

This project now has an automated Google Drive backup path under:

`FACTORY[NO DELETE]/Auto_Investing/projects/ib-trading-bot`

## What is backed up
- Full project worktree snapshot as `tar.zst`
- Git bundle for independent history recovery
- Encrypted environment archive for `.env` and local settings
- Codex profile essentials (`~/.codex/config.toml`, `skills`, `automations`, `memories`)
- Restore guide, latest status docs, and machine metadata

## What is intentionally excluded
- `node_modules/`
- `.venv/`
- `output/`
- logs and caches
- plaintext `.env` files from the full snapshot

## Sensitive data handling
- `.env` and `.claude/settings.local.json` are stored only in the encrypted env archive.
- The decryption key is stored locally at:

`~/.codex-backup-secrets/ib-trading-bot.recovery-key`

Save that key into a password manager or offline vault. It is not copied into Google Drive.

## Commands
Run a one-time backup:

```bash
python3 /Users/sehee/Desktop/SUB_Factory/Auto_Cash/ib-trading-bot/scripts/backup_codex_project.py run
```

Install the hourly launchd automation:

```bash
python3 /Users/sehee/Desktop/SUB_Factory/Auto_Cash/ib-trading-bot/scripts/backup_codex_project.py install-launchd
```

Check backup status:

```bash
python3 /Users/sehee/Desktop/SUB_Factory/Auto_Cash/ib-trading-bot/scripts/backup_codex_project.py status
```

Restore onto a new machine:

```bash
python3 restore_codex_project.py --project-name ib-trading-bot --target ~/Desktop/ib-trading-bot
```
