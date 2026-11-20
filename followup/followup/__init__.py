"""Automated client follow-up emails for small businesses.

Each module does one job:
    config.py     - load and check one client's settings
    jobs.py       - read and write the jobs list (CSV for now)
    sequence.py   - decide which email (if any) is due for a job today
    templates.py  - fill placeholders and build the final email text
    log.py        - record every email sent, plus errors
    sender.py     - "send" in dry-run mode (print) or for real (Gmail)
"""
