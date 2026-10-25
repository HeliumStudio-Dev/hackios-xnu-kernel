#!/usr/bin/env python3
"""Independent SAE PTK, EAPOL and BIP fixtures using hashlib and cryptography."""
import hashlib
import hmac
import struct
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.keywrap import aes_key_wrap
from cryptography.hazmat.primitives.asymmetric import ec


def emit(name, data):
    print(f'static const unsigned char {name}[] = {{' + ','.join(str(x) for x in data) + '};')


def cmac(key, data):
    c = CMAC(algorithms.AES(key))
    c.update(data)
    return c.finalize()


pmk = bytes(range(32))
own, peer = bytes.fromhex('020000000001'), bytes.fromhex('020000000002')
snonce, anonce = bytes(range(32, 64)), bytes(range(64, 96))
context = min(own, peer) + max(own, peer) + min(snonce, anonce) + max(snonce, anonce)
ptk = b''.join(hmac.new(pmk, struct.pack('<H', i) + b'Pairwise key expansion' + context + struct.pack('<H', 384),
                        hashlib.sha256).digest() for i in (1, 2))[:48]
kck, kek, tk = ptk[:16], ptk[16:32], ptk[32:]
rsn = bytes.fromhex('301a0100000fac040100000fac040100000fac08c0000000000fac06')
gtk, igtk = bytes(range(96, 112)), bytes(range(112, 128))
key_data = rsn + bytes.fromhex('dd16000fac010100') + gtk + bytes.fromhex('dd1c000fac090400010000000000') + igtk
if len(key_data) % 8:
    key_data += b'\xdd' + bytes(7 - len(key_data) % 8)


def message(info, replay, nonce, data=b'', sign=False):
    body = struct.pack('>BHHQ32s16s8s8s16sH', 2, info, 16, replay, nonce, bytes(16), bytes(8), bytes(8), bytes(16), len(data)) + data
    frame = bytearray(struct.pack('>BBH', 2, 3, len(body)) + body)
    if sign:
        frame[81:97] = cmac(kck, frame)
    return bytes(frame)


def rekey(counter, data):
    if len(data) % 8:
        data += b'\xdd' + bytes(7 - len(data) % 8)
    return message(0x1380, counter, bytes(32), aes_key_wrap(kek, data), True)


m1 = message(0x88, 1, anonce)
m2 = message(0x108, 1, snonce, rsn, True)
m3 = message(0x13c8, 2, anonce, aes_key_wrap(kek, key_data), True)
m4 = message(0x308, 2, bytes(32), b'', True)
# The station's replies leave Key Length zero; it is not used to carry the CCMP key size.
for name in ('m2', 'm4'):
    frame = bytearray(locals()[name])
    frame[7:9] = b'\0\0'
    frame[81:97] = bytes(16)
    frame[81:97] = cmac(kck, frame)
    globals()[name] = bytes(frame)
deauth = bytearray(bytes.fromhex('c0000000ffffffffffff') + peer + peer + bytes(2) + b'\x03\0' +
                   bytes.fromhex('4c100400020000000000') + bytes(8))
aad = bytes(deauth[:2]) + bytes(deauth[4:22]) + bytes(deauth[24:])
deauth[-8:] = cmac(igtk, aad)[:8]
same_rekey = rekey(3, bytes.fromhex('dd16000fac010100') + gtk + bytes.fromhex('dd1c000fac090400000000000000') + igtk)
igtk_only = rekey(4, bytes.fromhex('dd1c000fac090400000000000000') + igtk)
bad_kde = rekey(5, bytes.fromhex('dd16000fac010100') + bytes(range(16)) + b'\x30\xff')
for name in ('pmk', 'own', 'peer', 'snonce', 'rsn', 'tk', 'gtk', 'igtk', 'm1', 'm2', 'm3', 'm4', 'deauth',
             'same_rekey', 'igtk_only', 'bad_kde'):
    emit(name, locals()[name])
for scalar in (1, 2):
    p = ec.derive_private_key(scalar, ec.SECP256R1()).public_key().public_numbers()
    emit(f'point{scalar}', p.x.to_bytes(32, 'big') + p.y.to_bytes(32, 'big'))
