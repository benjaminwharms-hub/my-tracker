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

## 5. Connect a business's Gmail (once per client)

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
scripts/                   connect_gmail.py, send_test_email.py
tests/                     python -m pytest
```
