"""MeshCore v1 room packets, matching MeshCore src/{Mesh,Identity,Utils}.cpp.

Uses the existing cryptography dependency; no firmware identity is overwritten.
"""
from dataclasses import dataclass
import hashlib
import hmac
import os
import struct
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def u32(value):
    return struct.pack('<I', value)


def stamp(data):
    if len(data) < 4:
        raise ValueError('Missing timestamp')
    return struct.unpack_from('<I', data)[0]


class Identity:
    def __init__(self, seed):
        self.seed = seed
        self.signer = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
        self.public = self.signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    @classmethod
    def generate(cls):
        while True:
            identity = cls(os.urandom(32))
            if identity.public[0] not in (0, 255):
                return identity

    def secret(self, public):
        if len(public) != 32:
            raise ValueError('Invalid public key')
        prime = 2**255 - 19
        y = int.from_bytes(public, 'little') & ((1 << 255) - 1)
        if y >= prime or y == 1:
            raise ValueError('Invalid Edwards public key')
        # MeshCore ed25519_key_exchange converts Edwards Y to Montgomery U.
        u = ((1 + y) * pow(1 - y, -1, prime) % prime).to_bytes(32, 'little')
        scalar = hashlib.sha512(self.seed).digest()[:32]
        return x25519.X25519PrivateKey.from_private_bytes(scalar).exchange(
            x25519.X25519PublicKey.from_public_bytes(u))

    def advert(self, name, now):
        app = b'\x83' + name.encode('utf-8')  # room + name, no invented location
        message = self.public + u32(now) + app
        return self.public + u32(now) + self.signer.sign(message) + app


def encrypt(secret, clear):
    padded = clear + bytes((-len(clear)) % 16)
    enc = Cipher(algorithms.AES(secret[:16]), modes.ECB()).encryptor()
    ciphertext = enc.update(padded) + enc.finalize()
    return hmac.digest(secret, ciphertext, 'sha256')[:2] + ciphertext


def decrypt(secret, data):
    if len(data) < 18 or (len(data) - 2) % 16:
        raise ValueError('Invalid encrypted packet length')
    if not hmac.compare_digest(data[:2], hmac.digest(secret, data[2:], 'sha256')[:2]):
        raise ValueError('Invalid packet MAC')
    dec = Cipher(algorithms.AES(secret[:16]), modes.ECB()).decryptor()
    return dec.update(data[2:]) + dec.finalize()


def path_length(encoded):
    size, count = (encoded >> 6) + 1, encoded & 63
    if size > 3 or count * size > 64:
        raise ValueError('Invalid path')
    return size * count


def transport_code(key, kind, payload):
    value = int.from_bytes(hmac.digest(key, bytes([kind]) + payload, 'sha256')[:2], 'little')
    return 1 if value == 0 else 65534 if value == 65535 else value


@dataclass
class Packet:
    kind: int
    payload: bytes
    route: int = 1
    path_code: int = 0
    path: bytes = b''
    codes: bytes = b''

    @classmethod
    def parse(cls, raw):
        if not 2 <= len(raw) <= 255 or raw[0] >> 6:
            raise ValueError('Invalid packet version/length')
        route = raw[0] & 3
        offset = 5 if route in (0, 3) else 1
        if len(raw) <= offset:
            raise ValueError('Truncated packet')
        size = path_length(raw[offset])
        end = offset + 1 + size
        if end >= len(raw) or len(raw[end:]) > 184:
            raise ValueError('Truncated/oversize payload')
        return cls((raw[0] >> 2) & 15, raw[end:], route, raw[offset], raw[offset+1:end], raw[1:5] if offset == 5 else b'')

    def encode(self, scope=None):
        route = self.route
        codes = self.codes
        if scope is not None and route == 1:
            route = 0
            codes = struct.pack('<HH', transport_code(scope, self.kind, self.payload), 0)
        if len(self.path) != path_length(self.path_code) or len(self.payload) > 184:
            raise ValueError('Packet too large')
        raw = bytes([(self.kind << 2) | route]) + (codes if route in (0, 3) else b'') + bytes([self.path_code]) + self.path + self.payload
        if len(raw) > 255:
            raise ValueError('Packet too large')
        return raw


def datagram(identity, peer, secret, kind, clear, path=None):
    packet = Packet(kind, peer[:1] + identity.public[:1] + encrypt(secret, clear))
    if path is not None:
        packet.route, packet.path_code, packet.path = 2, path[0], path[1]
    return packet


def ack(clear, public):
    return hashlib.sha256(clear + public).digest()[:4]
