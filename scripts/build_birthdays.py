#!/usr/bin/env python3
"""Build the Faith Students birthday calendar (birthdays.ics) from Planning Center.

Pulls everyone in the PCO list "SM – Students & Leaders" and marks anyone also
in "SM – Student Roster" as a student; everyone else is a leader.

Students appear by first and last name; leaders by full name plus "(Leader)".
No birth years, ages, grades, or contact info are published.

Needs two environment variables (a PCO Personal Access Token):
  PCO_APP_ID, PCO_SECRET
Usage: python3 build_birthdays.py OUTPUT_PATH
"""
import base64, datetime, json, os, sys, time, urllib.request

STUDENTS_AND_LEADERS_LIST = "4716088"  # SM – Students & Leaders
STUDENT_ROSTER_LIST = "4077479"        # SM – Student Roster
API = "https://api.planningcenteronline.com/people/v2"

auth = base64.b64encode(f"{os.environ['PCO_APP_ID']}:{os.environ['PCO_SECRET']}".encode()).decode()


def call(url, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"Authorization": f"Basic {auth}"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited
                time.sleep(int(e.headers.get("Retry-After", "20")))
                continue
            raise
    raise RuntimeError(f"Gave up on {url}")


def refresh(list_id):
    """Re-run the list rules so newly added people show up."""
    try:
        call(f"{API}/lists/{list_id}/run", method="POST")
    except Exception as e:  # not fatal; we'll use the list as it stands
        print(f"warning: could not refresh list {list_id}: {e}")


def list_people(list_id):
    url = f"{API}/lists/{list_id}/people?per_page=100"
    out = []
    while url:
        page = call(url)
        out.extend(page.get("data", []))
        url = page.get("links", {}).get("next")
    return out


def esc(text):
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")


def main(out_path):
    refresh(STUDENT_ROSTER_LIST)
    time.sleep(20)
    refresh(STUDENTS_AND_LEADERS_LIST)
    time.sleep(20)

    roster_ids = {p["id"] for p in list_people(STUDENT_ROSTER_LIST)}
    everyone = list_people(STUDENTS_AND_LEADERS_LIST)
    if not everyone:
        sys.exit("List came back empty; refusing to publish an empty calendar.")

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Faith Students//Birthdays//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:Faith Students Birthdays", "X-WR-TIMEZONE:America/Detroit",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H",
    ]
    count = skipped = 0
    for p in everyone:
        a = p["attributes"]
        bd = a.get("birthdate")
        if not bd:
            skipped += 1
            continue
        _, m, d = map(int, bd.split("-"))
        first = (a.get("nickname") or a.get("first_name") or "").strip()
        last = (a.get("last_name") or "").strip()
        name = f"{first} {last}".strip()
        title = f"🎂 {name}" if p["id"] in roster_ids else f"🎂 {name} (Leader)"
        start = datetime.date(2024, m, d)  # 2024 is a leap year, so Feb 29 is valid
        end = start + datetime.timedelta(days=1)
        rrule = "RRULE:FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=-1" if (m, d) == (2, 29) else "RRULE:FREQ=YEARLY"
        lines += [
            "BEGIN:VEVENT", f"UID:bday-{p['id']}@faithrh.com", f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{start:%Y%m%d}", f"DTEND;VALUE=DATE:{end:%Y%m%d}", rrule,
            f"SUMMARY:{esc(title)}", "TRANSP:TRANSPARENT", "END:VEVENT",
        ]
        count += 1
    lines.append("END:VCALENDAR")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(lines) + "\r\n")
    print(f"Wrote {count} birthdays to {out_path} ({skipped} people had no birthdate in PCO).")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "birthdays.ics")
