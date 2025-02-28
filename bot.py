from slack_bolt import App
from datetime import datetime, timedelta
import os
import re
import logging
import pytz

app = App(token=os.environ.get("SLACK_BOT_TOKEN"), signing_secret=os.environ.get("SLACK_SIGNING_SECRET"))

LOCAL_TZ = pytz.timezone('US/Eastern')

equipment_status = {
    "pelotonmast": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "pelotontank": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "treadmill": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "fanbike": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "cablemachine": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "rower": {"user": None, "end_time": None, "waitlist": [], "reservations": []}
}

def parse_time(time_str):
    logging.debug(f"Parsing time string: {time_str}")
    now = datetime.now(LOCAL_TZ)
    max_future = now + timedelta(hours=12)

    if "tomorrow" in time_str:
        day = now + timedelta(days=1)
        time_part = time_str.replace("tomorrow", "").strip()
        logging.debug(f"Detected 'tomorrow', using day: {day.strftime('%Y-%m-%d')}")
    else:
        day = now
        time_part = time_str
        logging.debug(f"Using current day: {day.strftime('%Y-%m-%d')}")

    match = re.match(r"(\d{1,2})(am|pm)", time_part)
    if not match:
        logging.debug("No valid time match found")
        return None
    hour, period = int(match.group(1)), match.group(2)
    if hour > 12 or hour < 1:
        logging.debug(f"Invalid hour: {hour}")
        return None
    if period == "pm" and hour != 12:
        hour += 12
    elif period == "am" and hour == 12:
        hour = 0
    result = LOCAL_TZ.localize(datetime(day.year, day.month, day.day, hour, 0))
    logging.debug(f"Parsed time: {result.strftime('%Y-%m-%d %H:%M %Z')}")
    if result > max_future:
        logging.debug(f"Time exceeds 12-hour limit: {result} > {max_future}")
        return None
    if result < now:
        logging.debug(f"Time is in the past: {result} < {now}")
        return None
    return result

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
        respond("Usage: /start [equipment] [minutes]\nOptions: pelotonmast, pelotontank, treadmill, fanbike, cablemachine, rower")
        return
    equip, duration_str = args[0], args[1]
    if equip not in equipment_status:
        respond("Invalid equipment. Options: pelotonmast, pelotontank, treadmill, fanbike, cablemachine, rower")
        return
    try:
        duration = int(duration_str.replace("min", "").strip())
    except ValueError:
        respond("Duration must be a number (e.g., 30 or 30min)")
        return
    if equipment_status[equip]["user"]:
        respond(f"{equip} is in use by <@{equipment_status[equip]['user']}> until {equipment_status[equip]['end_time'].strftime('%d-%b %H:%M')}.")
        return
    user = command["user_id"]
    start_time = datetime.now(LOCAL_TZ)
    end_time = start_time + timedelta(minutes=duration)
    if not is_slot_free(equip, start_time, end_time):
        respond(f"{equip} is reserved during that time. Check /check.")
        return
    equipment_status[equip]["user"] = user
    equipment_status[equip]["end_time"] = end_time
    respond(f"<@{user}> started {equip} for {duration} min. Free at {end_time.strftime('%d-%b %H:%M')}.")
    app.client.chat_postMessage(channel="#gym-status", text=f"<@{user}> started {equip} until {end_time.strftime('%d-%b %H:%M')}")

@app.command("/finish")
def finish_equipment(ack, respond, command):
    ack()
    equip = command["text"].strip()
    if equip not in equipment_status:
        respond("Usage: /finish [equipment]\nOptions: pelotonmast, pelotontank, treadmill, fanbike, cablemachine, rower")
        return
    user = command["user_id"]
    if equipment_status[equip]["user"] != user:
        respond(f"You’re not using {equip}!")
        return
    equipment_status[equip]["user"] = None
    equipment_status[equip]["end_time"] = None
    waitlist = equipment_status[equip]["waitlist"]
    if waitlist:
        next_user = waitlist.pop(0)
        respond(f"{equip} is free! <@{next_user}>, you’re up!")
        app.client.chat_postMessage(channel="#gym-status", text=f"{equip} is free! <@{next_user}>, you’re up!")
    else:
        respond(f"{equip} is free!")
        app.client.chat_postMessage(channel="#gym-status", text=f"{equip} is free!")

@app.command("/wait")
def wait_equipment(ack, respond, command):
    ack()
    equip = command["text"].strip()
    if equip not in equipment_status:
        respond("Usage: /wait [equipment]\nOptions: pelotonmast, pelotontank, treadmill, fanbike, cablemachine, rower")
        return
    user = command["user_id"]
    if equipment_status[equip]["user"] == user:
        respond(f"You’re already using {equip}!")
        return
    if user in equipment_status[equip]["waitlist"]:
        respond(f"You’re already on the waitlist for {equip}!")
        return
    equipment_status[equip]["waitlist"].append(user)
    position = len(equipment_status[equip]["waitlist"])
    respond(f"Added to {equip} waitlist (Position {position}).")
    app.client.chat_postMessage(channel="#gym-status", text=f"<@{user}> joined {equip} waitlist (Position {position}).")

@app.command("/reserve")
def reserve_equipment(ack, respond, command):
    ack()
    text = command["text"].strip()
    parts = text.split()
    if len(parts) < 3:
        respond("Usage: /reserve [equipment] [time] [minutes]\nExamples: /reserve pelotonmast 4pm 30min, /reserve pelotontank tomorrow 6am 30min")
        return
    equip = parts[0]
    duration_str = parts[-1]
    time_str = " ".join(parts[1:-1])
    if equip not in equipment_status:
        respond("Invalid equipment. Options: pelotonmast, pelotontank, treadmill, fanbike, cablemachine, rower")
        return
    start_time = parse_time(time_str)
    if not start_time:
        respond("Invalid time format or beyond 12 hours. Use e.g., 4pm, tomorrow 6am (within 12 hours from now).")
        return
    try:
        duration = int(duration_str.replace("min", "").strip())
    except ValueError:
        respond("Duration must be a number (e.g., 30 or 30min)")
        return
    end_time = start_time + timedelta(minutes=duration)
    if start_time < datetime.now(LOCAL_TZ):
        respond("Can’t reserve in the past!")
        return
    user = command["user_id"]
    if not is_slot_free(equip, start_time, end_time):
        respond(f"{equip} is booked or in use from {start_time.strftime('%d-%b %H:%M')} to {end_time.strftime('%d-%b %H:%M')}. Check /check.")
        return
    reservation = {"user": user, "start_time": start_time, "end_time": end_time}
    equipment_status[equip]["reservations"].append(reservation)
    respond(f"<@{user}> reserved {equip} from {start_time.strftime('%d-%b %H:%M')} to {end_time.strftime('%d-%b %H:%M')}.")
    app.client.chat_postMessage(channel="#gym-status", text=f"<@{user}> reserved {equip} from {start_time.strftime('%d-%b %H:%M')} to {end_time.strftime('%d-%b %H:%M')}")

@app.command("/cancel")
def cancel_reservation(ack, respond, command):
    ack()
    args = command["text"].split()
    if len(args) != 2:
        respond("Usage: /cancel [equipment] [start_time]\nExample: /cancel pelotontank 4pm")
        return
    equip, time_str = args[0], args[1]
    if equip not in equipment_status:
        respond("Invalid equipment. Options: pelotonmast, pelotontank, treadmill, fanbike, cablemachine, rower")
        return
    start_time = parse_time(time_str)
    if not start_time:
        respond("Invalid time format. Use e.g., 4pm or tomorrow 6am.")
        return
    user = command["user_id"]
    reservations = equipment_status[equip]["reservations"]
    for i, res in enumerate(reservations):
        if res["user"] == user and res["start_time"] == start_time:
            del reservations[i]
            respond(f"<@{user}> canceled reservation for {equip} at {start_time.strftime('%d-%b %H:%M')}.")
            app.client.chat_postMessage(channel="#gym-status", text=f"<@{user}> canceled reservation for {equip} at {start_time.strftime('%d-%b %H:%M')}.")
            return
    respond(f"No reservation found for {equip} at {start_time.strftime('%d-%b %H:%M')} by <@{user}>.")

@app.command("/check")
def show_status(ack, respond, command):
    ack()
    status_msg = "Equipment Status:\n"
    now = datetime.now(LOCAL_TZ)
    for equip, info in equipment_status.items():
        status_msg += f"{equip}:\n"
        if info["user"]:
            status_msg += f"  Current: <@{info['user']}> until {info['end_time'].astimezone(LOCAL_TZ).strftime('%d-%b %H:%M')}\n"
        else:
            status_msg += "  Current: Free\n"
        status_msg += f"  Waitlist: {len(info['waitlist'])}\n"
        if info["reservations"]:
            status_msg += "  Reservations:\n"
            for res in sorted(info["reservations"], key=lambda x: x["start_time"]):
                if res["end_time"] > now:
                    status_msg += f"    <@{res['user']}> {res['start_time'].astimezone(LOCAL_TZ).strftime('%d-%b %H:%M')} - {res['end_time'].astimezone(LOCAL_TZ).strftime('%d-%b %H:%M')}\n"
    respond(status_msg)

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    port = int(os.environ.get("PORT", 3000))
    logging.debug(f"Starting Bolt app on port {port}")
    app.start(port=port)