You are setting up an automated customer follow-up email system for a small business on THIS computer. I'm the installer (I run this service for the business). Work through the steps below in order. Before each step, tell me in one short line what you're doing. If a step fails, show me the exact error and ask me before trying anything unusual.

RULES
- Never send any email to a customer during setup. The only email you may send is the test email, to {{ALERT_EMAIL}}.
- Don't change the program's code. Only create the files these steps describe.
- Never print, show or copy the contents of any token.json file.
- Use the commands for this computer's system (Windows: PowerShell; Mac: Terminal/zsh).
- "INSTALL DIR" means: Windows %USERPROFILE%\FollowupEmails; Mac ~/FollowupEmails.

STEP 1: Ask me for the business details (one message, all at once)
Ask me for: business name, the Gmail address the emails will be sent from, the sender name customers will see, the Google review link, phone, website (optional), the email signature (a few lines), and the daily send time (default 09:00). The alert email is {{ALERT_EMAIL}} unless I say otherwise. Detect the computer's timezone yourself (IANA name, e.g. America/Chicago) and show it to me with the details. Wait for my answers.

STEP 2: Make sure Python 3.10 or newer is installed
Check with "python --version" / "py -3 --version" (Windows) or "python3 --version" (Mac).
If it's missing or older: on Windows run
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
then use the full path of the new python.exe, since PATH won't update in this session. On a Mac, use Homebrew if it's installed ("brew install python@3.12"). Otherwise ask me to install Python from https://www.python.org/downloads/macos/ and tell you when it's done.

STEP 3: Download the program
Download this zip to a temporary folder and extract it:
  {{SOURCE_URL}}
Inside it, find the folder named "followup" that contains setup_wizard.py. Copy that folder's CONTENTS into INSTALL DIR.
If INSTALL DIR already exists, this is an update: copy over the program files, but keep the existing "clients", "secrets", "logs" and ".venv" folders exactly as they are.
Delete the temporary download afterwards.

STEP 4: Add the Google app key
Create the file INSTALL DIR/secrets/client_secret.json with exactly this content (it identifies my Google app; it does not give access to any mailbox):
{{CLIENT_SECRET_JSON}}

STEP 5: Install the Python packages
In INSTALL DIR: create a virtual environment named .venv (if it doesn't exist), then run
  <.venv python> -m pip install -r requirements.txt
<.venv python> is .venv\Scripts\python.exe on Windows and .venv/bin/python on a Mac. Use it for every command from now on, run from INSTALL DIR.

STEP 6: Run the setup (connects Gmail, schedules the daily run)
Write my answers from step 1 to a temporary JSON file OUTSIDE the install folder, with the keys: business_name, from_email, from_name, review_link, phone, website, timezone, signature (use \n between lines), alert_email.
Then TELL ME, before running anything: "A browser window will open. The business owner must sign in with <the Gmail> and click Allow. If Google says the app isn't verified, click Advanced, then Go to." Then run (with a 10-minute timeout, because it waits for the sign-in):
  <.venv python> setup_wizard.py --answers <that json file> --test-to {{ALERT_EMAIL}} --time <the send time>
After it finishes, delete the JSON file. If the output says "Couldn't schedule it automatically" or anything else failed, show me that part.
Check the daily schedule exists: Windows "schtasks /Query /TN FollowupEmails"; Mac "launchctl list | grep com.followup.daily".

STEP 7: Import the customer list
Ask me for the customer/job list file (Excel .xlsx or .csv). I'll give you its path or drag it into the chat. If it's another format (Numbers, Google Sheets, PDF), help me save it as .xlsx or .csv first.
Find the business's client folder name: the folder inside INSTALL DIR/clients. First run a PREVIEW:
  <.venv python> scripts/import_jobs.py --client <client folder name> "<file path>" --preview
Show me which columns were matched, which were ignored, the counts and any skipped rows. If the name or email column wasn't found, or a column is clearly matched wrongly, re-run with --map options, e.g. --map customer_email="E-mail" --map job_type="Work Done".
Then ask me: "Customers whose jobs are already complete are imported as finished, so they get NO emails. Do you want recently completed customers to get the emails still due (the 14-day review request, for example) instead?" If I say yes, add --email-recent-past.
When I confirm, run the same command without --preview.

STEP 8: Show me what will happen
Run:  <.venv python> run.py --all --dry-run
This only prints; it sends nothing. Summarise for me which customers would get which email today, and whether there were errors.

STEP 9: Finish
Give me a short summary: the install folder, the client folder, the daily send time, the "Follow-up Jobs" desktop shortcut (it opens jobs.csv), where the log is (INSTALL DIR/logs/daily.log), and whether the test email was sent to {{ALERT_EMAIL}}. Then give me 3 short lines I can read to the business owner on how to mark a job complete: open Follow-up Jobs, set status to "complete", save, keeping the CSV format.
