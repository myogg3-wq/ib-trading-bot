## Signal Loom Transfer Notes

This archive is intended to let another machine continue development quickly.

Included:
- Source code
- Tests
- Scripts
- Current `.env`
- Git history
- Runtime/output artifacts

Excluded:
- `.venv`
- `.playwright-cli`
- Python cache files

Project root:
- `/Users/sehee/Desktop/SUB_Factory/ib-trading-bot`

Recommended first steps on the new machine:
1. Extract the archive.
2. Create a fresh virtual environment in the project root.
3. Install dependencies with `pip install -r requirements.txt`.
4. Review `.env` and update any machine-specific values.
5. Start the preview server from the project root.

Preview app:
- Signal Loom web platform lives under `app/web`.

Important current status:
- Google login UI is wired for Signal Loom only.
- Google OAuth still needs a valid client ID/secret from the Signal Loom Google Cloud project.
- Admin dashboard is available through the platform account menu if `PLATFORM_ADMIN_TOKEN` is set.
