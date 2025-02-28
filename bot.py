from slack_bolt import App
import logging

app = App(token=os.environ.get("SLACK_BOT_TOKEN"), signing_secret=os.environ.get("SLACK_SIGNING_SECRET"))

@app.command("/start")
def simple_start(ack, respond):
    ack()
    respond("Hello, world!")

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    port = int(os.environ.get("PORT", 3000))
    logging.debug(f"Starting Bolt app on port {port}")
    app.start(port=port)