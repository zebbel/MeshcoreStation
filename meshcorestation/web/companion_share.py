"""Create a local QR contact card using MeshCore's documented contact URL."""
import base64
import re
from urllib.parse import urlencode


def contact_card(settings):
    import qrcode
    from qrcode.image.svg import SvgPathFillImage

    key = settings.get('public_key', '')
    name = settings.get('name', '')
    if not isinstance(key, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', key):
        raise ValueError('Invalid companion public key')
    if not isinstance(name, str) or not name or len(name.encode('utf-8')) > 31:
        raise ValueError('Invalid companion name')
    uri = 'meshcore://contact/add?' + urlencode({'name': name, 'public_key': key.lower(), 'type': 1})
    image = qrcode.make(uri, image_factory=SvgPathFillImage, border=4)
    svg = image.to_string()
    return {'ok': True, 'name': name, 'public_key': key.lower(), 'uri': uri,
            'image': 'data:image/svg+xml;base64,' + base64.b64encode(svg).decode('ascii')}
