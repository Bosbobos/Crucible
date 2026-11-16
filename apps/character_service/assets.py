"""Статусы изображений независимы от косметических прав."""
import json
from pathlib import Path
from functools import lru_cache

MANIFEST = Path(__file__).with_name('asset-manifest.json')


@lru_cache(maxsize=2)
def manifest_data(revision):
    return json.loads(MANIFEST.read_text()) if MANIFEST.is_file() else {'assets':{}}


def representation(item):
    manifest = manifest_data(MANIFEST.stat().st_mtime_ns if MANIFEST.exists() else 0)
    asset = manifest['assets'].get(item['asset_id'],{})
    part = asset.get('parts',{}).get(item['render_part'],{})
    return {'art_status':part.get('status',asset.get('status','missing')),
            'rendered':False,'representation':part if part.get('status')=='runtime_ready' else None,
            'icon_path':part.get('icon_path') if part.get('status')=='runtime_ready' else None}
