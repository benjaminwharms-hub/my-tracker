"""Decide which email, if any, is due for a job today.

This file is pure logic: it doesn't read files or send anything, so it's
easy to test. Given:
    - the client's stages (e.g. Day 1, 7, 14, 90)
    - how many days ago the job was completed
    - which stages this customer has already been sent
it answers: send a stage today, wait, or the sequence is finished.

The rules:
  1. Find the LATEST stage whose day has arrived.
  2. If it was already sent: wait for the next one, or finish if it was the last.
  3. If it hasn't been sent and is no more than `grace_days` late: send it.
     Any earlier stages that were never sent are skipped. A customer never
     gets a backlog of emails in one go.
  4. If it's more than `grace_days` late: skip it. Wait for the next stage,
     or finish if it was the last.
"""

from dataclasses import dataclass, field
from datetime import date

SEND = "send"
WAIT = "wait"
FINISH = "finish"


@dataclass
class Decision:
    action: str  # SEND, WAIT or FINISH
    stage: object = None  # the Stage to send (only when action == SEND)
    skipped: list = field(default_factory=list)  # earlier stages that are being passed over
    reason: str = ""  # plain-English explanation, for the console and the logs


def days_since(completion: date, today: date) -> int:
    return (today - completion).days


def decide(stages: list, days: int, already_sent: set, grace_days: int) -> Decision:
    """stages must be sorted by day (load_config does this). already_sent holds stage names."""
    arrived = [s for s in stages if s.day <= days]
    if not arrived:
        return Decision(WAIT, reason=f"day {days}: first email is due on day {stages[0].day}")

    latest = arrived[-1]
    is_last = latest is stages[-1]
    unsent_earlier = [s for s in arrived[:-1] if s.name not in already_sent]

    if latest.name in already_sent:
        if is_last:
            return Decision(FINISH, reason="all emails sent")
        return Decision(WAIT, reason=f"'{latest.name}' already sent; next is day {_next_day(stages, latest)}")

    days_late = days - latest.day
    if days_late <= grace_days:
        why = f"day {days}: '{latest.name}' is due"
        if days_late:
            why += f" ({days_late} day(s) late)"
        return Decision(SEND, stage=latest, skipped=unsent_earlier, reason=why)

    # Too late for this stage.
    skipped = unsent_earlier + [latest]
    if is_last:
        return Decision(FINISH, skipped=skipped,
                        reason=f"day {days}: last email is {days_late} days late (limit {grace_days}); not sending")
    return Decision(WAIT, skipped=skipped,
                    reason=f"day {days}: '{latest.name}' is too late to send; next is day {_next_day(stages, latest)}")


def _next_day(stages: list, current) -> int:
    i = stages.index(current)
    return stages[i + 1].day
