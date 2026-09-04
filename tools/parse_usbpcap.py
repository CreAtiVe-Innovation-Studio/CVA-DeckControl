#!/usr/bin/env python3
"""Parst USBPcap-pcapng-Dateien ohne tshark/wireshark - reiner Python-Parser
fuer den USBPcap-Frame-Header (siehe USBPcap-Projekt, offene Struktur):

Offset  Size  Feld
0       2     headerLen (u16 LE) - Gesamtlaenge des Headers inkl. evtl. Extra-Felder
2       8     irpId (u64 LE)
10      4     status (u32 LE)
14      2     function (u16 LE)
16      1     info (u8) - Bit0: 1=Device->Host (IN), 0=Host->Device (OUT)
17      2     bus (u16 LE)
19      2     device (u16 LE)
21      1     endpoint (u8, Bit7 oft zusaetzlich Richtung)
22      1     transfer (u8) - 0=Isochronous,1=Interrupt,2=Control,3=Bulk (USBPcap-Konvention)
23      4     dataLength (u32 LE) - Laenge der Nutzdaten NACH dem Header

Nach den ersten 27 Bytes koennen bei Control-Transfers noch Setup-Packet-Felder folgen
(headerLen > 27), danach beginnt die eigentliche Nutzlast (dataLength Bytes).
"""
import struct
import sys
from scapy.all import rdpcap

TRANSFER_NAMES = {0: "ISOCH", 1: "INTERRUPT", 2: "CONTROL", 3: "BULK"}

def parse_frame(raw: bytes):
    if len(raw) < 27:
        return None
    header_len = struct.unpack_from('<H', raw, 0)[0]
    irp_id = struct.unpack_from('<Q', raw, 2)[0]
    status = struct.unpack_from('<I', raw, 10)[0]
    function = struct.unpack_from('<H', raw, 14)[0]
    info = raw[16]
    bus = struct.unpack_from('<H', raw, 17)[0]
    device = struct.unpack_from('<H', raw, 19)[0]
    endpoint = raw[21]
    transfer = raw[22]
    data_length = struct.unpack_from('<I', raw, 23)[0]
    payload = raw[header_len:header_len + data_length]
    direction = "IN(dev->host)" if (info & 0x01) else "OUT(host->dev)"
    return {
        "header_len": header_len,
        "irp_id": irp_id,
        "status": status,
        "function": function,
        "info": info,
        "direction": direction,
        "bus": bus,
        "device": device,
        "endpoint": endpoint & 0x7F,
        "endpoint_raw": endpoint,
        "transfer": transfer,
        "transfer_name": TRANSFER_NAMES.get(transfer, f"?{transfer}"),
        "data_length": data_length,
        "payload": payload,
        "raw_header": raw[:header_len],
    }

def load(path):
    pkts = rdpcap(path)
    out = []
    for p in pkts:
        raw = bytes(p)
        f = parse_frame(raw)
        if f:
            out.append(f)
    return out

if __name__ == "__main__":
    path = sys.argv[1]
    frames = load(path)
    print(f"{len(frames)} frames")
    for i, f in enumerate(frames):
        print(f"[{i:4}] bus={f['bus']} dev={f['device']} ep=0x{f['endpoint_raw']:02x} "
              f"{f['transfer_name']:10} {f['direction']:15} len={f['data_length']:5} "
              f"payload[:24]={f['payload'][:24].hex()}")
