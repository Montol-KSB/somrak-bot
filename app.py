from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Server is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def server_on():
    # 👇 make the thread daemon so it won't block process exit
    t = Thread(target=run, daemon=True)
    t.start()
