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
        respond("Usage: /start [equipment] [minutes]\nOptions: pelotonmast, treadmill, fanbike, cablemachine, pelotontank, rower")
        return
    equip, duration_str = args[0], args[1]
    if equip not in equipment_status:
        respond("Invalid equipment. Options: pelotonmast, treadmill, fanbike, cablemachine, pelotontank, rower")
        return
    try:
        duration = int(duration_str.replace("min", "").strip())
    except ValueError:
        respond("Duration must be a number (e.g., 30 or 30min)")
        return
    if equipment_status[equip]["user"]:
        respond(f"{equip} is in use by <@{equipment_status[equip]['user']}> until {equipment_status[equip]['end_time'].strftime('%H:%M')}.")
        return
    user = command["user_id"]
    end_time = datetime.now() + timedelta(minutes=duration)
    if not is_slot_free(equip, datetime.now(), end_time):
        respond(f"{equip} is reserved during that time. Check /check.")
        return
    equipment_status[equip]["user"] = user
    equipment_status[equip]["end_time"] = end_time
    respond(f"<@{user}> started {equip} for {duration} min. Free at {end_time.strftime('%H:%M')}.")
    app.client.chat_postMessage(channel="#gym-status", text=f"<@{user}> started {equip} until {end_time.strftime('%H:%M')}.")

@app.command("/done")
def done_equipment(ack, respond, command):
    ack()
    equip = command["text"].strip()
    if equip not in equipment_status:
        respond("Usage: /done [equipment]\nOptions: pelotonmast, treadmill, fanbike, cablemachine, pelotontank, rower")
        return
    user = command["user_id"]
    if equipment_status[equip]["user"] != user:
        respond(f"You’re not using {equip}!")
        return
    equipment_status[equip]["user"] = None
    waitlist = equipment_status[equip]["waitlist"]
    if waitlist:
        next_user = waitlist.pop(0)
        respond(f"{equip} is free! <@{next_user}>, you’re up!")
        app.client.chat_postMessage(channel="#gym-status", text=f"{equip} is free! <@{next_user}>, you’re up!")
    else:
        respond(f"{equip} is free!")
        app.client.chat_postMessage(channel="#gym-status", text=f"{equip