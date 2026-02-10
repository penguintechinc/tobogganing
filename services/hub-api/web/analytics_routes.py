"""Web routes for analytics dashboard."""

from py4web import action, request, response, redirect, URL
from py4web.utils.form import Form, FormStyleBulma
from web.auth import get_current_user, user_manager


@action('analytics')
@action.uses('analytics.html')
def analytics_dashboard():
    """Analytics dashboard page."""
    # Check authentication
    user = get_current_user()
    if not user:
        redirect(URL('login'))
        return
    
    # Check if user has access to analytics (could be role-based)
    if not user_manager.has_permission(user, 'reporter'):
        redirect(URL('dashboard'))
        return
    
    return {
        'user': user,
        'title': 'Analytics Dashboard'
    }


@action('analytics/client/<client_id>')
@action.uses('client_detail.html')
def client_detail(client_id):
    """Detailed client information page."""
    # Check authentication
    user = get_current_user()
    if not user:
        redirect(URL('login'))
        return
    
    # Check permissions
    if not user_manager.has_permission(user, 'reporter'):
        redirect(URL('dashboard'))
        return
    
    return {
        'user': user,
        'client_id': client_id,
        'title': f'Client Details - {client_id}'
    }


@action('analytics/headend/<headend_id>')
@action.uses('headend_detail.html')
def headend_detail(headend_id):
    """Detailed headend information page."""
    # Check authentication
    user = get_current_user()
    if not user:
        redirect(URL('login'))
        return
    
    # Check permissions
    if not user_manager.has_permission(user, 'reporter'):
        redirect(URL('dashboard'))
        return
    
    return {
        'user': user,
        'headend_id': headend_id,
        'title': f'Headend Details - {headend_id}'
    }