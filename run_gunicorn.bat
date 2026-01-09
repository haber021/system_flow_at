@echo off
REM Lightweight Windows fallback for local testing. Gunicorn is Unix-only.
REM For production on Linux, use run_gunicorn.sh after installing dependencies.

SET PORT=8000
IF NOT "%1"=="" SET PORT=%1

echo Running Django development server on 0.0.0.0:%PORT% (development only)
python manage.py runserver 0.0.0.0:%PORT%
