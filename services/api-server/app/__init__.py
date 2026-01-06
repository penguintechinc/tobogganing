"""Tobogganing API Server"""

from flask import Flask
from flask_security import Security


def create_app():
    """Application factory"""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'placeholder'

    # Flask-Security-Too setup placeholder
    security = Security(app)

    return app
