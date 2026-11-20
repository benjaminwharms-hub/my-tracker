"""The daily run for one client: go through the jobs, and send whatever is due.

This is where the pieces come together:
    jobs.py      -> which jobs are complete
    log.py       -> what has already been sent, and who unsubscribed
    sequence.py  -> what is due today
    templates.py -> the email text
    sender.py    -> print it (dry run) or send it (Gmail)
"""

from dataclasses import dataclass, field
from datetime import date

from . import jobs as jobs_mod
from .log import ERROR, SENT, SKIPPED, STOPPED, SendLog, UnsubscribeList
from .sequence import FINISH, SEND, days_since, decide
from .templates import build_email, check_all_templates

# Values the system writes into the followup_stage column (besides stage names).
STARTED = "started"
DONE = "done"
STOPPED_REPLIED = "stopped_replied"
STOPPED_UNSUB = "stopped_unsubscribed"
FINAL_STATES = {DONE, STOPPED_REPLIED, STOPPED_UNSUB}


@dataclass
class Summary:
    sent: int = 0
    stopped: int = 0
    finished: int = 0
    errors: list = field(default_factory=list)


def run_client(cfg, today: date, sender, inbox, dry_run: bool, out=print) -> Summary:
    """Process one client's jobs for `today`. In dry-run mode, no files are changed."""
    check_all_templates(cfg)  # a template typo stops the run before anything is sent
    rows, columns = jobs_mod.load_jobs(cfg.jobs_path)
    log = SendLog(cfg.log_path, cfg.client_id, write_to_disk=not dry_run)
    unsubscribed = UnsubscribeList(cfg.unsubscribe_path, write_to_disk=not dry_run)
    summary = Summary()

    for row in rows:
        try:
            _process_job(cfg, row, today, sender, inbox, log, unsubscribed, summary, out)
        except Exception as e:  # one bad job must not stop the others
            msg = f"{type(e).__name__}: {e}"
            summary.errors.append(f"job {row['job_id']}: {msg}")
            log.record(row["job_id"], row["customer_email"], "", ERROR, detail=msg)
            out(f"  ! job {row['job_id']}: ERROR {msg}")

    if not dry_run:
        jobs_mod.save_jobs(cfg.jobs_path, rows, columns)
    return summary


def _process_job(cfg, row, today, sender, inbox, log, unsubscribed, summary, out):
    job_id = row["job_id"]
    email = row["customer_email"].strip().lower()
    label = f"  job {job_id} ({row['customer_name'] or '?'})"

    # 1. Only completed jobs that haven't already finished or stopped.
    if not jobs_mod.is_complete(row) or row["followup_stage"] in FINAL_STATES:
        return

    problem = jobs_mod.row_problem(row)
    if problem:
        raise ValueError(f"can't use this row: {problem}")

    # 2. A newly completed job: start its sequence. No date given means "completed today".
    if not row["completion_date"]:
        row["completion_date"] = today.isoformat()
    if not row["followup_stage"]:
        row["followup_stage"] = STARTED
        out(f"{label}: marked complete, starting sequence")
    completion = jobs_mod.parse_date(row["completion_date"])

    # 3. Unsubscribed earlier (possibly from a different job)?
    if email in unsubscribed:
        _stop(row, log, summary, STOPPED_UNSUB, "on unsubscribe list", label, out)
        return

    # 4. Which stages has this person already had?
    if cfg.dedupe_by == "email":
        already = log.sent_stages(email=email)
    else:
        already = log.sent_stages(job_id=job_id)
    already |= _stages_implied_by_column(cfg, row["followup_stage"])

    days = days_since(completion, today)
    decision = decide(cfg.stages, days, already, cfg.grace_days)

    for s in decision.skipped:
        if s.name not in already and not _skip_logged(log, job_id, s.name):
            log.record(job_id, email, s.name, SKIPPED, detail="too late to send")

    if decision.action == FINISH:
        row["followup_stage"] = DONE
        summary.finished += 1
        out(f"{label}: sequence finished ({decision.reason})")
        return
    if decision.action != SEND:
        out(f"{label}: nothing due ({decision.reason})")
        return

    # 5. Before sending: has the customer replied or asked to stop?
    #    Only after we've emailed them, since a message from them before that isn't a reply.
    if already:
        since = log.first_sent_date(email=email) or completion.isoformat()
        stop = inbox.check_stop(email, since)
        if stop == "unsubscribed":
            unsubscribed.add(email, f"replied STOP (job {job_id})")
            _stop(row, log, summary, STOPPED_UNSUB, "customer asked to unsubscribe", label, out)
            return
        if stop == "replied":
            _stop(row, log, summary, STOPPED_REPLIED, "customer replied", label, out)
            return

    # 6. Build and send the email, and log it straight away.
    stage = decision.stage
    message = build_email(cfg, stage, row, completion)
    message_id = sender.send(cfg, message)
    log.record(job_id, email, stage.name, SENT, message_id=message_id, detail=decision.reason)
    row["followup_stage"] = DONE if stage is cfg.stages[-1] else stage.name
    summary.sent += 1
    out(f"{label}: sent '{stage.name}' to {email} ({decision.reason})")


def _stop(row, log, summary, state, why, label, out):
    row["followup_stage"] = state
    log.record(row["job_id"], row["customer_email"], "", STOPPED, detail=why)
    summary.stopped += 1
    out(f"{label}: sequence stopped ({why})")


def _stages_implied_by_column(cfg, column_value) -> set:
    """If followup_stage says e.g. 'check_in', treat that stage and all earlier ones as sent.

    This lets you add existing customers part-way through a sequence, and it's
    a second safety net alongside the log.
    """
    names = [s.name for s in cfg.stages]
    if column_value in names:
        return set(names[: names.index(column_value) + 1])
    return set()


def _skip_logged(log, job_id, stage_name) -> bool:
    return any(r["job_id"] == job_id and r["stage"] == stage_name and r["result"] == SKIPPED for r in log.rows)
