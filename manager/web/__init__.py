# Web interface module for SASEWaddle Manager

from py4web import action, request, response, redirect, Field, Session, URL, T
from py4web.utils.form import Form, FormStyleDefault
from py4web.utils.cors import cors
from py4web.utils.auth import Auth
import os
import json
from datetime import datetime

from database import get_db
from ..security.middleware import security_fixture, require_admin_role


@action('security', method=['GET'])
@action.uses('security.html', security_fixture)
@require_admin_role
def security_dashboard():
    """Security management dashboard."""
    return dict(
        title="Security Management",
        description="Monitor and manage security systems, rate limiting, and DDoS protection"
    )


@action('admin', method=['GET'])
@action.uses('admin.html', security_fixture)
@require_admin_role  
def admin_dashboard():
    """Main admin dashboard."""
    return dict(
        title="Admin Dashboard",
        description="SASEWaddle Manager Administration"
    )