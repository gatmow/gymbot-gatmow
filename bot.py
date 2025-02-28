from slack_bolt import App
from datetime import datetime, timedelta
import os
import re
import logging
import pytz

app = App(token=os.environ.get("SLACK_BOT_TOKEN"), signing_secret=os.environ.get("SLACK_SIGNING_SECRET"))

LOCAL_TZ = pytz.timezone('US/Eastern')

equipment_status = {
    "PelotonMast": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "PelotonTank": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "Treadmill": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "FanBike": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "CableMachine": {"user": None, "end_time": None, "waitlist": [], "reservations": []},
    "Rower": {"user": None, "end_time": None, "waitlist": [], "reservations": []}
}

def parse_time(time_str):
    logging.debug(f"Parsing time string: {time_str}")
    now = datetime.now(LOCAL_TZ)
    max_future = now + timedelta(hours=24)

    if "tomorrow" in time_str.lower():
        day = now + timedelta(days=1)
        time_part = time_str.lower().replace("tomorrow", "").strip()
        logging.debug(f"Detected 'tomorrow', using day: {day.strftime('%Y-%m-%d')}")
    else:
        day = now
        time_part = time_str
        logging.debug(f"Using current day: {day.strftime('%Y-%m-%d')}")

    match = re.match(r"(\d{1,2})(?::(\d{2}))?(am|pm)", time_part.lower())
    if not match:
        logging.debug("No valid time match found")
        return None
    hour, minutes, period = int(match.group(1)), match.group(2) or "00", match.group(3)
    minutes = int(minutes)
    if hour > 12 or hour < 1 or minutes >= 60:
        logging.debug(f"Invalid time: hour={hour}, minutes={minutes}")
        return None
    if period == "pm" and hour != 12:
        hour += 12
    elif period == "am" and hour == 12:
        hour = 0
    result = LOCAL_TZ.localize(datetime(day.year, day.month, day.day, hour, minutes))
    logging.debug(f"Parsed time: {result.strftime('%Y-%m-%d %H:%M %Z')}")
    if result > max_future:
        logging.debug(f"Time exceeds 24-hour limit: {result} > {max_future}")
        return None
    if result < now:
        logging.debug(f"Time is in the past: {result} < {now}")
        return None
    return result

def get_equipment_key(equip_lower):
    """Helper to map lowercase equip to the original capitalized key."""
    for key in equipment_status:
        if key.lower() == equip_lower:
            return key
    return None

def is_slot_free(equip, start_time, end_time):
    equip_key = get_equipment_key(equip.lower())
    if not equip_key:
        return False
    current_user = equipment_status[equip_key].get("user")
    if current_user and equipment_status[equip_key]["end_time"] > start_time:
        return False
    for res in equipment_status[equip_key].get("reservations", []):
        res_start, res_end = res["start_time"], res["end_time"]
        if (start_time < res_end) and (end_time > res_start):
            return False
    return True

def clean_reservations():
    now = datetime.now(LOCAL_TZ)
    for equip in equipment_status:
        equipment_status[equip]["reservations"] = [res for res in equipment_status[equip]["reservations"] if res["end_time"] > now]

@app.command("/help")
def show_help(ack, respond, command):
    ack()
    respond("Here’s how to use the GymBot:\n"
            "- `/start [equipment] [minutes]` - Start now (e.g., `/start PelotonMast 30min`)\n"
            "- `/finish [equipment]` - End use (e.g., `/finish pelotonmast`)\n"
            "- `/wait [equipment]` - Join waitlist (e.g., `/wait Treadmill`)\n"
            "- `/reserve [equipment] [time] [minutes]` - Book ahead (e.g., `/reserve PelotonTank tomorrow 8:30pm 60min`)\n"
            "- `/cancel [equipment] [start_time optional]` - Cancel (e.g., `/cancel pelotontank` or `/cancel PelotonTank tomorrow 6am`)\n"
            "- `/check` - See status\n"
            "Equipment: PelotonMast, PelotonTank, Treadmill, FanBike, CableMachine, Rower (case doesn’t matter!)")

@app.command("/start")
def start_equipment(ack, respond, command):
    ack()
    args = command["text"].split()
    if len(args) != 2:
        respond("Usage: /start [equipment] [minutes]\nOptions: PelotonMast, PelotonTank, Treadmill, FanBike, CableMachine, Rower")
        return
    equip = args[0].lower()
    duration_str = args[1]
    equip_key = get_equipment_key(equip)
    if not equip_key:
        respond("Invalid equipment. Options: PelotonMast, PelotonTank, Treadmill, FanBike, CableMachine, Rower")
        return
    try:
        duration = int(duration_str.replace("min", "").strip())
    except ValueError:
        respond("Duration must be a number (e.g., 30 or 60min)")
        return
    if equipment_status[equip_key]["user"]:
        respond(f"{equip_key} is in use by <@{equipment_status[equip_key]['user']}> until {equipment_status[equip_key]['end_time'].strftime('%d-%b %-I:%M%p').lower()}.")
        return
    user = command["user_id"]
    start_time = datetime.now(LOCAL_TZ)
    end_time = start_time + timedelta(minutes=duration)
    if not is_slot_free(equip, start_time, end_time):
        respond(f"{equip_key} is reserved during that time. Check /check.")
        return
    equipment_status[equip_key]["user"] = user
    equipment_status[equip_key]["end_time"] = end_time
    respond(f"<@{user}> started {equip_key} for {duration} min. Free at {end_time.strftime('%d-%b %-I:%M%p').lower()}.")
    app.client.chat_postMessage(channel="#gym-status", text=f"<@{user}> started {equip_key} until {end_time.strftime('%d-%b %-I:%M%p').lower()}")

@app.command("/finish")
def finish_equipment(ack, respond, command):
    ack()
    equip = command["text"].strip().lower()
    equip_key = get_equipment_key(equip)
    if not equip_key:
        respond("Usage: /finish [equipment]\nOptions: PelotonMast, PelotonTank, Treadmill, FanBike, CableMachine, Rower")
        return
    user = command["user_id"]
    if equipment_status[equip_key]["user"] != user:
        respond(f"You’re not using {equip_key}!")
        return
    equipment_status[equip_key]["user"] = None
    equipment_status[equip_key]["end_time"] = None
    waitlist = equipment_status[equip_key]["waitlist"]
    if waitlist:
        next_user = waitlist.pop(0)
        duration = 30
        start_time = datetime.now(LOCAL_TZ)
        end_time = start_time + timedelta(minutes=duration)
        if is_slot_free(equip, start_time, end_time):
            equipment_status[equip_key]["user"] = next_user
            equipment_status[equip_key]["end_time"] = end_time
            respond(f"{equip_key} is free! <@{next_user}> auto-started for {duration} min, free at {end_time.strftime('%d-%b %-I:%M%p').lower()}.")
            app.client.chat_postMessage(channel="#gym-status", text=f"<@{next_user}> auto-started {equip_key} until {end_time.strftime('%d-%b %-I:%M%p').lower()} (from waitlist).")
        else:
            respond(f"{equip_key} is free! <@{next_user}>, you’re up, but it’s reserved soon—use /start.")
            app.client.chat_postMessage(channel="#gym-status", text=f"{equip_key} is free! <@{next_user}>, you’re up!")
    else:
        respond(f"{equip_key} is free!")
        app.client.chat_postMessage(channel="#gym-status", text=f"{equip_key} is free!")

@app.command("/wait")
def wait_equipment(ack, say, command):
    ack()
    equip = command["text"].strip().lower()
    equip_key = get_equipment_key(equip)
    if not equip_key:
        say("Usage: /wait [equipment]\nOptions: PelotonMast, PelotonTank, Treadmill, FanBike, CableMachine, Rower")
        return
    user = command["user_id"]
    if equipment_status[equip_key]["user"] == user:
        say(f"You’re already using {equip_key}!")
        return
    if user in equipment_status[equip_key]["waitlist"]:
        say(f"You’re already on the waitlist for {equip_key}!")
        return
    equipment_status[equip_key]["waitlist"].append(user)
    position = len(equipment_status[equip_key]["waitlist"])
    say(channel="#gym-status", text=f"<@{user}> joined {equip_key} waitlist (Position {position}).")

@app.command("/reserve")
def reserve_equipment(ack, respond, command):
    ack()
    text = command["text"].strip()
    parts = text.split()
    if len(parts) < 3:
        respond("Usage: /reserve [equipment] [time] [minutes]\nExamples: /reserve PelotonMast 8:30pm 60min, /reserve PelotonTank tomorrow 6am 30min")
        return
    equip = parts[0].lower()
    duration_str = parts[-1]
    time_str = " ".join(parts[1:-1])
    logging.debug(f"Equip before check: {equip}")
    equip_key = get_equipment_key(equip)
    if not equip_key:
        respond("Invalid equipment. Options: PelotonMast, PelotonTank, Treadmill, FanBike, CableMachine, Rower")
        return
    start_time = parse_time(time_str)
    if not start_time:
        respond("Invalid time format or beyond 24 hours. Use e.g., 8pm, 8:30pm, tomorrow 6am (within 24 hours).")
        return
    try:
        duration = int(duration_str.replace("min", "").strip())
    except ValueError:
        respond("Duration must be a number (e.g., 30 or 60min)")
        return
    end_time = start_time + timedelta(minutes=duration)
    if start_time < datetime.now(LOCAL_TZ):
        respond("Can’t reserve in the past!")
        return
    user = command["user_id"]
    if not is_slot_free(equip, start_time, end_time):
        respond(f"{equip_key} is booked or in use from {start_time.strftime('%d-%B %-I:%M%p').lower()} to {end_time.strftime('%d-%B %-I:%M%p').lower()}. Check /check.")
        return
    reservation = {"user": user, "start_time": start_time, "end_time": end_time}
    logging.debug(f"Appending reservation for {equip_key}")
    equipment_status[equip_key]["reservations"].append(reservation)
    respond(f"<@{user}> reserved {equip_key} from {start_time.strftime('%d-%b %-I:%M%p').lower()} to {end_time.strftime('%d-%b %-I:%M%p').lower()}.")
    app.client.chat_postMessage(channel="#gym-status", text=f"<@{user}> reserved {equip_key} from {start_time.strftime('%d-%b %-I:%M%p')} to {end_time.strftime('%d-%b %-I:%M%p')}")

@app.command("/cancel")
def cancel_reservation(ack, respond, command):
    ack()
    text = command["text"].strip()
    args = text.split()
    if len(args) < 1:
        respond("Usage: /cancel [equipment] [start_time optional]\nExamples: /cancel PelotonTank, /cancel pelotontank tomorrow 6am")
        return
    equip = args[0].lower()
    equip_key = get_equipment_key(equip)
    if not equip_key:
        respond("Invalid equipment. Options: PelotonMast, PelotonTank, Treadmill, FanBike, CableMachine, Rower")
        return
    user = command["user_id"]
    reservations = equipment_status[equip_key]["reservations"]
    if len(args) == 1:
        upcoming = [res for res in reservations if res["user"] == user and res["start_time"] > datetime.now(LOCAL_TZ)]
        if not upcoming:
            respond(f"No upcoming reservations found for {equip_key} by <@{user}>.")
            return
        next_res = min(upcoming, key=lambda x: x["start_time"])
        reservations.remove(next_res)
        respond(f"<@{user}> canceled next reservation for {equip_key} at {next_res['start_time'].strftime('%d-%b %-I:%M%p').lower()}.")
        app.client.chat_postMessage(channel="#gym-status", text=f"<@{user}> canceled reservation for {equip_key} at {next_res['start_time'].strftime('%d-%b %-I:%M%p')}")
    else:
        time_str = " ".join(args[1:])
        start_time = parse_time(time_str)
        if not start_time:
            respond("Invalid time format. Use e.g., 8pm, 8:30pm, or tomorrow 6am.")
            return
        for i, res in enumerate(reservations):
            if res["user"] == user and res["start_time"] == start_time:
                del reservations[i]
                respond(f"<@{user}> canceled reservation for {equip_key} at {start_time.strftime('%d-%b %-I:%M%p').lower()}.")
                app.client.chat_postMessage(channel="#gym-status", text=f"<@{user}> canceled reservation for {equip_key} at {start_time.strftime('%d-%b %-I:%M%p')}")
                return
        respond(f"No reservation found for {equip_key} at {start_time.strftime('%d-%b %-I:%M%p').lower()} by <@{user}>.")

@app.command("/check")
def show_status(ack, respond, command):
    ack()
    clean_reservations()
    status_msg = "Equipment Status:\n"
    now = datetime.now(LOCAL_TZ)
    for equip in equipment_status:
        status_msg += f"{equip}:\n"
        if equipment_status[equip]["user"]:
            status_msg += f"  Current: <@{equipment_status[equip]['user']}> until {equipment_status[equip]['end_time'].astimezone(LOCAL_TZ).strftime('%d-%b %-I:%M%p').lower()}\n"
        else:
            status_msg += "  Current: Free\n"
        status_msg += f"  Waitlist: {len(equipment_status[equip]['waitlist'])}\n"
        if equipment_status[equip]["reservations"]:
            status_msg += "  Reservations:\n"
            for res in sorted(equipment_status[equip]["reservations"], key=lambda x: x["start_time"]):
                if res["end_time"] > now:
                    status_msg += f"    <@{res['user']}> {res['start_time'].astimezone(LOCAL_TZ).strftime('%d-%b %-I:%M%p').lower()} - {res['end_time'].astimezone(LOCAL_TZ).strftime('%d-%b %-I:%M%p').lower()}\n"
    respond(status_msg)

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    port = int(os.environ.get("PORT", 3000))
    logging.debug(f"Starting Bolt app on port {port}")
    app.start(port=port)