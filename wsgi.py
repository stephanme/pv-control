# gunicorn --bind 0.0.0.0:8080 wsgi:app

from pvcontrol import app

if __name__ == "__main__":
    app.run()