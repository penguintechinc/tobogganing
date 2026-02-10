"""Main py4web application entry point for SASEWaddle Manager."""

import os
import sys
import logging
from py4web import action, request, response, abort, redirect, URL
from py4web.core import _before_request, _after_request
from py4web.utils.auth import Auth
from py4web.utils.cors import cors

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import all modules to register routes
from . import web
from .api import analytics_routes, security_routes, backup_routes
from .security.middleware import security_fixture

logger.info("SASEWaddle Manager application initialized")


@action('/')
def index():
    """Main index page - redirect to admin dashboard."""
    return redirect(URL('admin'))


@action('health', method=['GET'])
@action.uses(cors())
def health_check():
    """Health check endpoint for load balancers."""
    return {
        'status': 'healthy',
        'service': 'sasewaddle-manager',
        'version': '1.0.0'
    }


@action('api/health', method=['GET'])
@action.uses(cors())  
def api_health_check():
    """API health check endpoint."""
    return {
        'status': 'healthy',
        'api_version': 'v1',
        'timestamp': request.now.isoformat()
    }