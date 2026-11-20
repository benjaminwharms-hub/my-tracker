"""Import a business's customer/job list (Excel .xlsx or .csv) into their jobs.csv.

    python scripts/import_jobs.py --client smith_roofing "C:/Users/Dave/Downloads/Customers.xlsx"

Column names are matched automatically (e.g. "Client", "E-mail Address",
"Date Completed"). If a column isn't recognised, name it yourself:
    --map customer_email="E-mail Addr" --map job_type="Work Done"

By default, jobs that are ALREADY complete are imported as finished
(followup_stage = done), so past customers aren't emailed. Add
--email-recent-past to let recently completed jobs get the emails that are due.

Use --preview to see what would happen without changing anything.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from followup.config import load_config  # noqa: E402
from followup.importer import import_file  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import a customer list into jobs.csv.")
    parser.add_argument("file", help="the .xlsx or .csv file")
    parser.add_argument("--client", required=True)
    parser.add_argument("--sheet", help="Excel sheet name (default: the first sheet)")
    parser.add_argument("--map", action="append", default=[], metavar='FIELD="Column name"',
                        help="say which column is which, e.g. customer_email=\"E-mail\"")
    parser.add_argument("--email-recent-past", action="store_true",
                        help="let already-complete jobs get any emails still due (default: no emails for them)")
    parser.add_argument("--preview", action="store_true", help="show what would be imported; change nothing")
    args = parser.parse_args(argv)

    mapping = {}
    for item in args.map:
        field, _, column = item.partition("=")
        mapping[field.strip()] = column.strip().strip('"')

    cfg = load_config(args.client)
    try:
        report = import_file(Path(args.file), cfg.jobs_path, mapping=mapping, sheet=args.sheet,
                             existing_done=not args.email_recent_past, write=not args.preview)
    except ValueError as e:
        print(f"Import problem: {e}")
        return 1

    print("Columns matched:")
    for field, column in report["columns_matched"].items():
        print(f"  {field:16} <- {column}")
    if report["columns_ignored"]:
        print(f"Columns not used: {', '.join(report['columns_ignored'])}")
    print(f"\n{'Would add' if args.preview else 'Added'} {report['added']} job(s):")
    print(f"  {report['added_complete_no_emails']} already complete -> marked done, no emails")
    print(f"  {report['added_will_get_emails']} already complete -> will get any email still due")
    print(f"  {report['added_not_complete']} not complete yet -> emails start when marked complete")
    if report["skipped"]:
        print(f"\nSkipped {len(report['skipped'])} row(s):")
        for line, who, why in report["skipped"]:
            print(f"  row {line} ({who}): {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
