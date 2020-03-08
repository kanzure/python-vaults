import struct
import hashlib

# ----
#
# This is from bitcoin's test_framework/messages.py
# required for ser_string

def ser_compact_size(l):
    r = b""
    if l < 253:
        r = struct.pack("B", l)
    elif l < 0x10000:
        r = struct.pack("<BH", 253, l)
    elif l < 0x100000000:
        r = struct.pack("<BI", 254, l)
    else:
        r = struct.pack("<BQ", 255, l)
    return r

def ser_string(s):
    return ser_compact_size(len(s)) + s

# ----

def sha256(data):
    """
    Compute the sha256 digest of the given data.

    returns bytes
    """
    return hashlib.sha256(data).digest()
