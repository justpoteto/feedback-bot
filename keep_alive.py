"""
Keep-Alive for render
"""

from flask import Flask
import subprocess

app = Flask('')

@app.route('/')
def index():
    return 'health'

if __name__ == "__main__":
    subprocess.Popen(["python","main.py"])

    app.run(host="0.0.0.0")