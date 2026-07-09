"""Pytest configuration for hub-api tests."""
import sys
import os

# Add parent directories to sys.path to allow imports from shared/ and hub-api modules
hub_api_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, hub_api_dir)
sys.path.insert(0, repo_root)
