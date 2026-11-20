# Automated client follow-up emails

When a job is marked **complete**, the business's customer gets a short sequence
of follow-up emails, sent from the business's own Gmail:

| Day | Stage            | Email                                      |
|-----|------------------|--------------------------------------------|
| 1   | `thank_you`      | Thank you for choosing us                  |
| 7   | `check_in`       | Is everything OK?                          |
| 14  | `review_request` | Please leave a Google review (with link)   |
| 90  | `referral`       | Seasonal maintenance and referrals         |

Safety built in:
- The sequence stops if the customer replies. Out-of-office auto-replies don't count.
- Replying STOP, or using Gmail's Unsubscribe button, adds the customer to a
  permanent do-not-email list for that business.
- Nobody is ever sent the same stage twice.
- If a job is entered late, the customer gets only the latest email that's due,
  never a backlog.
- Every send, skip, stop and error is recorded in `send_log.csv`.

---

## 1. Install

You need Python 3.10 or newer.

```bash
cd followup
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest                 # all tests should pass
```

## 2. Try it safely (dry run)

A dry run prints the emails instead of sending them, and changes no files:

```bash
python run.py --client example_builder --dry-run
python run.py --client example_builder --dry-run --today 2026-12-04   # pretend it's another day
python run.py --all --dry-run                                         # every client
```

## 3. Add a client business

1. Copy `clients/example_builder/` to `clients/<new_id>/`, e.g. `clients/smith_roofing/`.
   The folder name is the client's ID.
2. Edit `config.yaml`: business name, `from_email` (their Gmail), review link,
   phone, signature, timezone.
3. Edit the emails in `templates/`. The first line is `Subject: ...`, then a
   blank line, then the body. Available placeholders:
   `{customer_name}` `{first_name}` `{job_type}` `{job_address}` `{completion_date}`
   `{business_name}` `{from_name}` `{review_link}` `{phone}` `{website}`.
   The signature and the unsubscribe line are added automatically.
4. Fill in `jobs.csv` (it opens in Excel or Google Sheets):

   | column            | who fills it | notes |
   |-------------------|--------------|-------|
   | `job_id`          | business     | any unique ID; left blank, one is generated |
   | `customer_name`   | business     | |
   | `customer_email`  | business     | |
   | `job_type`        | business     | e.g. "deck build" |
   | `job_address`     | business     | |
   | `completion_date` | business     | `YYYY-MM-DD` or `M/D/YYYY`; left blank, today is used |
   | `status`          | business     | set to `complete` to start the emails |
   | `followup_stage`  | **system**   | last stage sent, `done`, `stopped_replied` or `stopped_unsubscribed` |

   You can add your own columns (e.g. `notes`); they're kept.
   To add an existing customer part-way through, type a stage name into
   `followup_stage` (e.g. `check_in`). That stage and the earlier ones then
   count as already sent.

> Real client folders hold customer data. `.gitignore` stops them from being
> committed to this (public) repo. Keep real client data in a **private** repo.

## 4. Gmail API setup (one time, for you as the operator)

You create **one** Google Cloud app. Every client business then signs in to it
with their own Gmail.

1. Go to <https://console.cloud.google.com/>, sign in, and **create a project**
   (e.g. "Client Follow-ups").
2. **Enable the Gmail API**: *APIs & Services → Library*, search "Gmail API" → **Enable**.
3. **Set up the consent screen** (*Google Auth Platform*, or *APIs & Services → OAuth consent screen*):
   - **Branding**: app name (e.g. "Follow-up Emails by <your company>"), your support email.
   - **Audience**: choose **External**. Your clients are separate businesses,
     even if they use Google Workspace.
   - **Data Access**: add the scopes `.../auth/gmail.send` and `.../auth/gmail.readonly`.
   - **Test users**: add each client's Gmail address while the app is in Testing.
4. **Create the OAuth client**: *Clients* (or *Credentials*) → **Create client** →
   type **Desktop app** → **Download JSON**.
5. Save the file as `followup/secrets/client_secret.json`. The `secrets/` folder
   is git-ignored. Never commit or email this file.

### Important: Testing vs In production
- **Testing** (the default): only listed test users can connect, and **Google
  expires their tokens after 7 days**. That's fine for trying things out, but
  not for real daily use.
- **In production** without verification: tokens don't expire. When a business
  connects, they'll see "Google hasn't verified this app". They click
  *Advanced → Go to (app name)* to continue. You can connect up to 100 users this way.
- **Verified**: removes the warning. `gmail.readonly` is a *restricted* scope,
  so verification needs a paid third-party security assessment. That's worth it
  once you have many clients, not before.

Push the app to production under *Audience → Publish app* once your own test works.

## 5. Install on a client's computer (the easy way)

This is the normal way to set up a client. Do section 4 once first, so that
`secrets/client_secret.json` exists.

1. **Build the package** on your computer:
   ```bash
   python scripts/make_package.py
   ```
   This creates `dist/FollowupEmails-installer.zip`. It contains the program,
   the starter email templates and your `client_secret.json`. It never contains
   tests, other clients' data or Gmail tokens.
2. **Add the business's Gmail as a test user** in Google Cloud, while your app
   is in Testing mode (section 4).
3. **On the client's computer**: copy the zip over, unzip it, and double-click
   - Windows: `Install (Windows).bat`. If you see "Windows protected your PC",
     click *More info → Run anyway*.
   - Mac: `Install (Mac).command`. If it "can't be opened", right-click it →
     *Open* → *Open*.
4. **Answer the wizard's questions.** It will:
   1. ask for the business details (name, Gmail, review link, phone, signature,
      and your email for problem alerts)
   2. create the business's folder in `~/FollowupEmails/clients/`
   3. open Google sign-in. The business signs in and clicks Allow.
   4. send a test email
   5. schedule the daily run (default 09:00)
   6. put a **Follow-up Jobs** shortcut to `jobs.csv` on the desktop

The installer installs Python first if it's missing. On Windows it does this
automatically; on a Mac it opens the python.org download page.

After install:
- Each day's output is added to `~/FollowupEmails/logs/daily.log`.
- If a run has problems, the system emails a warning to `alert_email`. The one
  exception: if Gmail itself is disconnected, no email can be sent, so the
  problem only shows in the log.
- **Updating** to a new version: build a new package and run the installer
  again. Settings, templates, the jobs list and the Gmail connection are kept.
- **Removing** the schedule: `python setup_wizard.py --uninstall` (from the
  `FollowupEmails` folder, using `.venv`'s Python).

Missed days: Windows runs a missed task as soon as the computer is back on.
A Mac runs it when it wakes from sleep, but not if it was fully shut down.
In that case it runs the next day. Either way, `grace_days` (default 7)
makes sure the late emails still go out.

## 5a. Or: set up with Claude by pasting one prompt

Instead of carrying the zip, you can have Claude do the whole install on the
client's computer.

**Once, on your computer**, after section 4:
```bash
python scripts/make_setup_prompt.py --alert-email you@yourbusiness.com
```
This writes `dist/claude_setup_prompt.txt`. It contains your Google app key
and the link Claude downloads the program from (this repo's current branch on
GitHub). Keep it private, and don't commit it: `dist/` is git-ignored.
Regenerate it if you move the code to another branch or repo.

**On the client's computer:**
1. Install the Claude desktop app, sign in (any account with Claude Code,
   including yours), and open the **Code** tab. Regular chat and Cowork can't
   install programs on the computer itself.
2. Pick the home folder as the working folder, and paste the whole prompt.
3. Answer Claude's questions (business details), and approve the commands it
   asks to run.
4. When Claude says so, the **business owner signs in to Gmail** in the
   browser and clicks Allow.
5. Give Claude the **customer list** (Excel or CSV, any column names). Claude
   previews the import, shows you how the columns were matched, and asks
   whether recently completed customers should get the emails still due.
6. Claude runs a dry run, shows you what would go out today, and summarises
   the setup.

The importer on its own: `python scripts/import_jobs.py --client <id> list.xlsx --preview`.
By default, customers whose jobs are already complete are imported as `done`,
so they get no emails. Add `--email-recent-past` to send them any email that's
still due.

## 5b. Connect or reconnect a business's Gmail by hand

```bash
python scripts/connect_gmail.py --client smith_roofing
```

A browser opens. The **business** signs in with the Gmail in their `from_email`
and clicks Allow. Do this together on a screen share, or have them sign in on
your computer; you never need their password. The token is saved to
`secrets/smith_roofing/token.json`. The script refuses to save it if they
signed in with a different account than `from_email`.

Then send yourself every email in the sequence to check how they look in a real inbox:

```bash
python scripts/send_test_email.py --client smith_roofing --to you@yourmail.com
```

## 6. First live run (suggested order)

```bash
python run.py --client smith_roofing --dry-run                # 1. check what would go out
python run.py --client smith_roofing --dry-run --live-inbox   # 2. same, but also read real replies (read-only)
python run.py --client smith_roofing                          # 3. send for real
```

Tip: for the very first real run, use a `jobs.csv` with your own email addresses as the customers.

## 7. Files the system writes (per client)

- `send_log.csv`: every email sent (who, which stage, when, Gmail message ID),
  plus skips, stops and errors.
- `unsubscribed.csv`: people who asked to stop. They're never emailed again by this business.
- `jobs.csv`: the `followup_stage` column (and a blank `completion_date` or `job_id` gets filled in).

## Settings reference (`config.yaml`)

| setting       | meaning |
|---------------|---------|
| `grace_days`  | how many days late an email may still go out (default 7) |
| `dedupe_by`   | `email` (default): never the same stage twice to one address. `job`: once per job, so repeat customers get a fresh sequence |
| `stages`      | the sequence: `name`, `day`, `template`. Add, remove or retime emails here |
| `timezone`    | decides what "today" is for the business, e.g. `America/Chicago` |

## How it works (for learning)

```
run.py                     command line: which clients, dry run or real
followup/runner.py         the daily loop over jobs (ties everything together)
followup/config.py         loads and checks config.yaml
followup/jobs.py           reads/writes jobs.csv
followup/sequence.py       pure logic: which stage is due today
followup/templates.py      fills placeholders, adds signature and unsubscribe line
followup/log.py            send_log.csv and unsubscribed.csv
followup/sender.py         dry-run printer (and the sender/inbox interface)
followup/gmail_client.py   OAuth, sending, reply/STOP detection
followup/client_setup.py   creates a client folder (used by the wizard)
followup/scheduler.py      Windows Task Scheduler / Mac launchd daily run
setup_wizard.py            the step-by-step setup on a client's computer
installers/                Install (Windows).bat, Install (Mac).command, READ ME FIRST.txt
followup/importer.py       imports a business's own Excel/CSV customer list
prompts/                   the Claude setup prompt template
scripts/                   connect_gmail.py, send_test_email.py, make_package.py,
                           make_setup_prompt.py, import_jobs.py
tests/                     python -m pytest
```
