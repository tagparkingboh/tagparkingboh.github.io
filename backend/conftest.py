"""
Pytest configuration for the TAG backend tests.
"""
import sys
from pathlib import Path

# Add the backend directory to the path
sys.path.insert(0, str(Path(__file__).parent))
