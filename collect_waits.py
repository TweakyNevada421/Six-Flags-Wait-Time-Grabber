#!/usr/bin/env python3
"""
Six Flags Over Texas wait-time logger.

Pulls current ride wait times from the Queue-Times.com API (park id 34) and
appends one row per ride to waits_log.csv. It only records on Fridays,
Saturdays and Sundays (Central Time), snaps each reading to a half-hour slot,
and skips a slot that has already been logged, so it is safe to schedule it
more often than every 30 minutes.

Data: "Powered by Queue-Times.com" (https://queue-times.com) - keep that
attribution if you share charts or results built from this data.

Needs only Python 3.9+ (standard library).

Usage:
    python collect_waits.py              # normal run (what the scheduler calls)
    python collect_waits.py --force      # ignore day/time window (for testing)
    python collect_waits.py --out my.csv --start 10:00 --end 23:30
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

PARK_ID = 34  # Six Flags Over Texas on Queue-Times.com
URL = f"https://queue-times.com/parks/{PARK_ID}/queue_times.json"
TZ = ZoneInfo("America/Chicago")
LOG_DAYS = {4, 5, 6}  # Mon=0 ... Fri=4, Sat=5, Sun=6
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

HEADER = [
    "timestamp_ct", "date", "day", "slot_time", "slot_key", "land",
    "ride_id", "ride", "is_open", "wait_min", "source_updated_utc",
]


def fetch():
    req = urllib.request.Request(
        URL, headers={"User-Agent": "personal-wait-time-logger/1.0"}
    )
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        except Exception as e:  # network hiccup: wait and retry
            last_err = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Could not fetch {URL}: {last_err}")


def parse_hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def already_logged(path, date_str, slot_time):
    if not os.path.exists(path):
        return False
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) > 3 and row[1] == date_str and row[3] == slot_time:
                return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="waits_log.csv")
    ap.add_argument("--start", default="10:00", help="first slot to log (CT)")
    ap.add_argument("--end", default="23:30", help="last slot to log (CT)")
    ap.add_argument("--force", action="store_true",
                    help="ignore the day/time window (testing)")
    args = ap.parse_args()

    now = datetime.now(TZ)
    minutes = now.hour * 60 + now.minute
    slot_minutes = (minutes // 30) * 30
    slot_time = f"{slot_minutes // 60:02d}:{slot_minutes % 60:02d}"
    slot_key = (slot_minutes // 60) * 100 + slot_minutes % 60  # e.g. 1330
    date_str = now.strftime("%Y-%m-%d")

    if not args.force:
        if now.weekday() not in LOG_DAYS:
            return 0
        if not (parse_hhmm(args.start) <= slot_minutes <= parse_hhmm(args.end)):
            return 0
        if already_logged(args.out, date_str, slot_time):
            return 0

    data = fetch()

    rows = []
    for land in data.get("lands", []):
        for r in land.get("rides", []):
            rows.append((land.get("name", ""), r))
    for r in data.get("rides", []):  # rides not assigned to a land
        rows.append(("(no land)", r))

    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    new_file = not os.path.exists(args.out)
    with open(args.out, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(HEADER)
        for land, r in rows:
            w.writerow([
                stamp, date_str, DAY_NAMES[now.weekday()], slot_time, slot_key,
                land, r.get("id"), r.get("name"),
                1 if r.get("is_open") else 0, r.get("wait_time", 0),
                r.get("last_updated", ""),
            ])
    print(f"{stamp}: logged {len(rows)} rides for slot {slot_time}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
