# Flask Backend (App-Specific Addendums)

## Quart Deviation from Flask Standard

Tobogganing uses **Quart** instead of Flask for the hub-api service.

### Rationale
- Quart is async-native (built on ASGI, not WSGI)
- API-compatible with Flask (same decorator patterns, Blueprint system)
- Required for high-throughput SASE policy distribution via gRPC streaming
- Native async support eliminates the thread pool overhead of Flask + gevent/eventlet
- Hypercorn ASGI server provides HTTP/2 support out of the box

### Key Differences from Flask Standard
- **Import**: `from quart import Quart` instead of `from flask import Flask`
- **ASGI Server**: Use `hypercorn` instead of `gunicorn`
- **Async Routes**: All route handlers are `async def`, use `await request.get_json()`
- **Auth**: Use `quart-auth` or Flask-Security-Too via `quart.flask_patch`
- **Testing**: Use `pytest-asyncio` with `app.test_client()` (async context)
- **Background Tasks**: Native `asyncio.create_task()` instead of Celery for lightweight tasks

### Flask-Security-Too Compatibility
Flask-Security-Too can work with Quart via the compatibility layer:
```python
import quart.flask_patch  # Must be imported before flask_security
from flask_security import Security, SQLAlchemyUserDatastore
```

If compatibility issues arise, fall back to `quart-auth` for session management
and implement RBAC manually using the existing JWT infrastructure.

### ASGI Server Configuration
```bash
# Development
hypercorn main:app --bind 0.0.0.0:8080 --reload

# Production
hypercorn main:app --bind 0.0.0.0:8080 --workers 4 --worker-class uvloop
```
