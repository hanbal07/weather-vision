"""WSGI entry point for the WeatherVision web application.

Deployment command::

    gunicorn wsgi:app --workers 1 --threads 4 --timeout 30

Local development::

    flask --app wsgi run
"""
from web_app import create_app

app = create_app()

if __name__ == "__main__":
    # Local development only. Production uses gunicorn (see Procfile).
    app.run(host="0.0.0.0", port=8000, debug=True)
