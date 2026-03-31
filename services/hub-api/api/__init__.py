"""Hub API package."""
from quart import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")
