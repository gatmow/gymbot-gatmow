from slack_bolt import App
from datetime import datetime, timedelta
import os
import re
import logging

app = App(token=os.environ.get("SLACK_BOT_TOKEN"), signing_secret=os.environ.get("SLACK_SIGNING_SECRET"))

equipment_status = {
    "pelotonmast": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "treadmill": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "fanbike": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "cablemachine": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "pelotontank": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "rower": {"user": None, "end_time": None, "waitlist": [], "reservations": []}
}

def parse_time(time_str):
    time_str = time_str.lower().replace(" ", "")
    match = re.match(r"(\d{1,2})(am|pm)", time_str)
    if not match:
        return None
    hour, period = int(match.group(1)), match.group(2)
    if hour > 12 or hour < 1:
        return None
    if period == "pm" and hour != 12:
        hour += 12
    elif period == "am" and hour == 12:
        hour = 0
    now = datetime.now()
    return datetime(now.year, now.month, now.day, hour, 0)

def is_slot_free(equip, start_time, end_time):
    current_user = equipment_status[equip]["user"]
    if current_user and equipment_status[equip]["end_time"] > start_time:
        return False
    for res in equipment_status[equip]["reservations"]:
        res_start, res_end = res["start_time"], res["end_time"]
        if (start_time < res_end) and (end_time > res_start):
            return False
    return True

@app.command("/start")
def start_equipment(ack, respond, command):
    ack()
    args = command["text"].split()
    if len(args) != 2:
        respond("Usage: /start [equipment] [minutes]\nOptions: pelotonmast, treadmill, fanbike, cablemachine,