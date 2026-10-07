"""Central paths and web settings. MeshcoreStation never loads legacy environment files."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv('MESHCORESTATION_DATA_DIR', str(ROOT / 'data'))).expanduser().resolve()
DB_PATH = DATA_DIR / 'meshcorestation.db'
TIMEZONE = ZoneInfo(os.getenv('MESHCORESTATION_TIMEZONE', 'Europe/Berlin'))
HOST = os.getenv('MESHCORESTATION_HOST', '0.0.0.0')
PORT = int(os.getenv('MESHCORESTATION_PORT', '80'))
if not 1 <= PORT <= 65535:
    raise ValueError('MESHCORESTATION_PORT must be between 1 and 65535')
