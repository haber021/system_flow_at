Enhancements: Multi-worker server and run scripts
-----------------------------------------------

What I added
- `gunicorn` and `uvicorn` to `pyproject.toml` dependencies for production servers.
- `run_gunicorn.sh` — shell script to start Gunicorn with multiple workers and threads.
- `run_gunicorn.bat` — Windows fallback that runs the Django dev server for local testing.

Quick usage
- Install dependencies (prefer virtualenv) and Gunicorn:

```bash
python -m pip install -r <(python - <<PY
import tomllib,sys
with open('pyproject.toml','rb') as f:
    data=tomllib.load(f)
deps=data.get('project',{}).get('dependencies',[])
print('\n'.join(deps))
PY
)
```

- Start on Linux/Unix:

```bash
WORKERS=5 THREADS=4 PORT=8000 ./run_gunicorn.sh
```

- Windows local test:

```powershell
.\run_gunicorn.bat 8000
```

Notes and recommendations
- Gunicorn is not supported on native Windows; run production servers on a Linux host.
- Put the app behind a reverse proxy (nginx) for TLS termination, connection buffering, and static files.
- Use HTTPS in production and set `SESSION_COOKIE_SECURE=True` and other secure settings in `core/settings.py`.
- For true horizontal scaling use a load balancer and multiple instances (containers or VMs) behind it.
