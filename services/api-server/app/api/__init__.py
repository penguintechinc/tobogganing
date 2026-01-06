"""API module initialization"""

from flask import Blueprint
from pydal import DAL

from .v1 import create_v1_blueprint


def create_api_blueprint(db: DAL) -> Blueprint:
    """Create main API blueprint with versioned sub-blueprints

    Args:
        db: PyDAL database instance

    Returns:
        Main API blueprint with v1 registered
    """
    api_bp = Blueprint('api', __name__, url_prefix='/api')

    # Register v1 blueprint
    v1_bp = create_v1_blueprint(db)
    api_bp.register_blueprint(v1_bp)

    return api_bp
