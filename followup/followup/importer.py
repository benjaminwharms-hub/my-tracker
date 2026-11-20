"""Import a business's own customer/job list (Excel or CSV) into jobs.csv.

Businesses name their columns all sorts of ways ("Client", "E-mail Address",
"Date Completed"...). This module matches common names automatically; you can
also say exactly which column is which with mapping={"customer_email": "E-mail Addr"}.

Safety: by default, imported jobs that are ALREADY complete are marked
followup_stage = "done", so importing a list of past customers sends nobody
anything. Only jobs marked complete from now on start a sequence. Pass
existing_done=False to send due emails to recent past customers too.
"""

import csv
import re
from datetime import date, datetime
from pathlib import Path

from .jobs import EMAIL_RE, is_complete, load_jobs, parse_date, save_jobs

# Column names we recognise, compared after lower-casing and removing spaces and punctuation.
ALIASES = {
    "job_id": ["jobid", "id", "jobnumber", "jobno", "invoice", "invoicenumber", "invoiceno", "workorder"],
    "customer_name": ["customername", "name", "client", "clientname", "customer", "fullname", "homeowner",
                      "contact", "contactname"],
    "first_name": ["firstname", "first", "givenname"],
    "last_name": ["lastname", "last", "surname", "familyname"],
    "customer_email": ["customeremail", "email", "emailaddress", "clientemail", "contactemail"],
    "job_type": ["jobtype", "service", "project", "projecttype", "worktype", "jobdescription",
                 "description", "type", "scope", "servicetype", "work", "workdone", "workperformed",
                 "servicesperformed", "job"],
    "job_address": ["jobaddress", "address", "siteaddress", "propertyaddress", "location", "street",
                    "streetaddress", "serviceaddress"],
    "completion_date": ["completiondate", "completed", "datecompleted", "completeddate", "finishdate",
                        "finished", "enddate", "datefinished", "jobdate", "date"],
    "status": ["status", "jobstatus", "stage", "state"],
}


def _norm(header: str) -> str:
    """'Job #' -> 'jobnumber', 'E-mail Address' -> 'emailaddress'."""
    return re.sub(r"[^a-z0-9]", "", str(header).lower().replace("#", "number"))


def read_table(path: Path, sheet: str = None) -> tuple:
    """Read a .csv or .xlsx file. Returns (headers, rows), where each row is a list of values."""
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb[sheet] if sheet else wb.worksheets[0]
        table = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
    elif path.suffix.lower() in (".csv", ".txt"):
        with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
            table = list(csv.reader(f))
    else:
        raise ValueError(f"Can't read {path.suffix} files. Save the list as .xlsx or .csv first.")

    # The header row is the first row with at least two filled cells (skips title rows).
    table = [r for r in table if any(c not in (None, "") for c in r)]
    for i, row in enumerate(table):
        if sum(c not in (None, "") for c in row) >= 2:
            headers = ["" if c is None else str(c).strip() for c in row]
            return headers, table[i + 1:]
    raise ValueError(f"{path.name} looks empty.")


def match_columns(headers: list, mapping: dict = None) -> dict:
    """Return {our field: column index}. Explicit mapping wins; then exact alias matches."""
    mapping = mapping or {}
    found = {}
    normed = [_norm(h) for h in headers]
    for field, column in mapping.items():
        if column not in headers:
            raise ValueError(f"Column '{column}' (for {field}) isn't in the file. Columns: {headers}")
        found[field] = headers.index(column)
    for field, aliases in ALIASES.items():
        if field in found:
            continue
        for alias in aliases:  # aliases are in order of preference
            if alias in normed and normed.index(alias) not in found.values():
                found[field] = normed.index(alias)
                break
    return found


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))  # Excel stores job number 1001 as 1001.0
    return str(value).strip()


def import_file(path: Path, jobs_path: Path, mapping: dict = None, sheet: str = None,
                existing_done: bool = True, write: bool = True) -> dict:
    """Add the rows from `path` to jobs.csv. Returns a report dict (see the keys at the end)."""
    headers, table = read_table(path, sheet)
    cols = match_columns(headers, mapping)

    has_name = "customer_name" in cols or "first_name" in cols
    if "customer_email" not in cols or not has_name:
        raise ValueError(f"Couldn't find the customer name and email columns. Columns in the file: {headers}. "
                         f"Say which is which, e.g. --map customer_email=\"E-mail\" --map customer_name=\"Client\"")

    rows, columns = load_jobs(jobs_path)
    known_ids = {r["job_id"] for r in rows}
    known_keys = {(r["customer_email"].lower(), r["completion_date"], r["job_type"].lower()) for r in rows}

    added, skipped = [], []
    for line_no, raw in enumerate(table, start=2):
        get = lambda field: _cell_text(raw[cols[field]]) if field in cols and cols[field] < len(raw) else ""
        name = get("customer_name") or " ".join(p for p in (get("first_name"), get("last_name")) if p)
        email = get("customer_email").lower()
        if not email:
            skipped.append((line_no, name or "?", "no email address"))
            continue
        if not EMAIL_RE.match(email):
            skipped.append((line_no, name or "?", f"email '{email}' doesn't look valid"))
            continue
        if not name:
            skipped.append((line_no, email, "no customer name"))
            continue

        completion = get("completion_date")
        if completion:
            try:
                completion = parse_date(completion).isoformat()
            except ValueError:
                skipped.append((line_no, name, f"can't read completion date '{completion}'"))
                continue

        # No status column: a row with a completion date counts as complete.
        status = get("status") or ("complete" if completion else "in progress")
        row = {c: "" for c in columns}
        row.update({
            "job_id": get("job_id") or f"IMP{len(rows) + len(added) + 1:04d}",
            "customer_name": name, "customer_email": email,
            "job_type": get("job_type"), "job_address": get("job_address"),
            "completion_date": completion, "status": status, "followup_stage": "",
        })
        if row["job_id"] in known_ids or (email, completion, row["job_type"].lower()) in known_keys:
            skipped.append((line_no, name, "already in the jobs list"))
            continue
        if existing_done and is_complete(row):
            row["followup_stage"] = "done"  # past customer: no emails
        known_ids.add(row["job_id"])
        known_keys.add((email, completion, row["job_type"].lower()))
        added.append(row)

    if write and added:
        save_jobs(jobs_path, rows + added, columns)

    return {
        "columns_matched": {f: headers[i] for f, i in cols.items()},
        "columns_ignored": [h for i, h in enumerate(headers) if h and i not in cols.values()],
        "added": len(added),
        "added_complete_no_emails": sum(r["followup_stage"] == "done" for r in added),
        "added_will_get_emails": sum(is_complete(r) and r["followup_stage"] == "" for r in added),
        "added_not_complete": sum(not is_complete(r) for r in added),
        "skipped": skipped,
    }
