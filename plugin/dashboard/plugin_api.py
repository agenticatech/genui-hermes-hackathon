"""Backend routes of the genui plugin, mounted at /api/plugins/genui/ in the process Desktop
connects to. The desktop half reaches them with ctx.rest()."""
import importlib.util
import socket
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from plugins.plugin_storage import plugin_data_dir

PLUGIN_DIR = Path(__file__).resolve().parent.parent


def _load_library():
    # This module is loaded on its own, outside the plugin package: load the shared library by path.
    spec = importlib.util.spec_from_file_location("genui_library", PLUGIN_DIR / "library.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


library = _load_library()
router = APIRouter()


@router.get("/ping")
async def ping():
    return {"ok": True, "host": socket.gethostname(), "time": time.time()}


@router.get("/component/{key}")
async def get_component(key: str):
    """One shown component as the Desktop half builds its frame: the stored record (type, props,
    rev, the model's id) plus the frame's document: the runtime and the theme that draws it."""
    if not library.KEY.match(key):
        raise HTTPException(400, "invalid component key")
    record = library.Store(plugin_data_dir("genui") / "components").get(key)
    if record is None:
        raise HTTPException(404, "unknown component")
    payload = library.frame_payload(record)
    if payload is None:
        raise HTTPException(500, f"no theme draws {record['type']}")
    return payload
