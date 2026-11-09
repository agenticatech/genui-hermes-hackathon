import sys
from pathlib import Path

# plugin/__init__.py needs Hermes; library.py does not, so the tests import it on its own.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
