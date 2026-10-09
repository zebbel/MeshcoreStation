"""Create dashboard release assets from a Heltec V4 USB PlatformIO build."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

TARGET = 'heltec_v4_companion_radio_usb'


def package(build, output):
    image = (build / 'firmware.bin').read_bytes()
    partitions = (build / 'partitions.bin').read_bytes()
    if len(image) < 64 or image[0] != 0xE9 or struct.unpack_from('<H', image, 12)[0] != 9 or image[32:36] != b'\x32\x54\xcd\xab':
        raise ValueError('Expected an ESP32-S3 app-only firmware.bin')
    if len(partitions) != 0xC00:
        raise ValueError('Expected a 3072-byte PlatformIO partition table')
    output.mkdir(parents=True, exist_ok=True)
    name = TARGET + '.bin'
    shutil.copyfile(build / 'firmware.bin', output / name)
    manifest = {'schema': 1, 'target': TARGET, 'chip': 'esp32s3', 'offset': 0x10000,
                'image': name, 'sha256': hashlib.sha256(image).hexdigest(),
                'partition_sha256': hashlib.sha256(partitions).hexdigest()}
    (output / (TARGET + '.json')).write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path, help='MeshCore/.pio/build/heltec_v4_companion_radio_usb')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    package(args.build, args.output)
