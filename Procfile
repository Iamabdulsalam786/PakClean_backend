# Render / Heroku-style process file.
# "web" = HTTP service. $PORT is injected by the platform (do not hardcode 8000).
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
