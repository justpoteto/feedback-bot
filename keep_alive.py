"""
Keep-Alive for render
"""

from flask import Flask

app = Flask('')

@app.route('/')
def index():
    return 'health'

if __name__ == "__main__":
    app.run(host="0.0.0.0")