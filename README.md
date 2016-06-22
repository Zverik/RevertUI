# Simple Revert UI

A web interface for [simple-revert](https://github.com/Zverik/simple-revert).
Uses SQLite for job management and imports simple_revert for actual reverting.

## Installation

1. Create a virtualenv and run `pip install -r requirements.txt`.
2. Add `revertui/revert_job.py` to crontab, minutely.
3. Add `revertui/revertui.wsgi` to your web server, or start `revertui/run.py` for debugging.
4. Go to http://localhost:5000 or wherever you installed the WSGI script, and revert something.

## Author and License

Written by Ilya Zverev, licensed WTFPL.
