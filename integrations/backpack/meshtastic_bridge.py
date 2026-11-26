#!/usr/bin/env python3
"""Local Meshtastic TCP receiver -> owner-only runtime IPC. No channel keys logged."""
import argparse
import json
from pathlib import Path
import socket
import time


def request(path, data):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(str(path))
        client.sendall(json.dumps(data, allow_nan=False).encode() + b'\n')
        with client.makefile('rb') as stream:
            reply = json.loads(stream.readline(1048577))
        if reply.get('error'):
            raise RuntimeError('Runtime rejected Meshtastic update')
        return reply


def packet_event(packet):
    decoded = packet.get('decoded', {})
    if decoded.get('portnum') != 'TEXT_MESSAGE_APP' or not isinstance(decoded.get('text'), str):
        return None
    sender = str(packet.get('fromId', packet.get('from', 'unknown')))[:64]
    identifier = packet.get('id')
    event = {'source': 'meshtastic', 'type': 'message.received', 'category': 'communication',
             'data': {'sender': sender, 'text': decoded['text'][:2000],
                      'channel': packet.get('channel'), 'snr': packet.get('rxSnr'),
                      'rssi': packet.get('rxRssi')}}
    # Include sender: packet IDs alone are not globally unique.
    if type(identifier) is int and identifier > 0:
        event['external_id'] = f'{sender}:{identifier}'
    observed = packet.get('rxTime')
    if type(observed) in (int, float) and 0 < observed <= time.time() + 300:
        event['observed_at'] = observed
    return event


class Frames:
    """Bounded incremental Meshtastic stream decoder; debug bytes are discarded."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        payloads = []
        while len(self.buffer) >= 4:
            if self.buffer[:2] != b'\x94\xc3':
                del self.buffer[0]
                continue
            length = int.from_bytes(self.buffer[2:4], 'big')
            if not 0 < length <= 512:
                del self.buffer[:2]
                continue
            if len(self.buffer) < length + 4:
                break
            payloads.append(bytes(self.buffer[4:length + 4]))
            del self.buffer[:length + 4]
        return payloads


def packet_from_proto(packet):
    if not packet.HasField('decoded') or packet.decoded.portnum != 1:
        return None
    return packet_event({
        'id': packet.id, 'fromId': f'!{getattr(packet, "from"):08x}',
        'channel': packet.channel, 'rxSnr': packet.rx_snr, 'rxRssi': packet.rx_rssi,
        'rxTime': packet.rx_time,
        'decoded': {'portnum': 'TEXT_MESSAGE_APP',
                    'text': packet.decoded.payload.decode('utf-8', errors='replace')}})


def serve(root):
    # Only protobuf definitions are used: the installed SDK heartbeat path is unreliable
    # with this daemon. Config snapshots/keys are parsed transiently and never retained.
    from meshtastic.protobuf import mesh_pb2
    from google.protobuf.message import DecodeError
    path = root / 'run/runtime.sock'
    queue = []
    dropped = 0
    connection = None
    frames = Frames()
    retry_at = next_config = health_at = verified_at = deadline = 0
    nonce = 0
    while True:
        now = time.monotonic()
        try:
            if connection is None and now >= retry_at:
                retry_at = now + 10
                connection = socket.create_connection(('127.0.0.1', 4403), timeout=3)
                connection.settimeout(.2)
                frames = Frames()
                next_config = verified_at = 0
            if connection is not None:
                if now >= next_config:
                    nonce = (nonce + 1) % 0xffffffff or 1
                    payload = mesh_pb2.ToRadio(want_config_id=nonce).SerializeToString()
                    connection.sendall(b'\x94\xc3' + len(payload).to_bytes(2, 'big') + payload)
                    deadline, next_config = now + 15, now + 20
                try:
                    data = connection.recv(4096)
                    if not data:
                        raise ConnectionError('Local daemon closed the stream')
                    for payload in frames.feed(data):
                        message = mesh_pb2.FromRadio()
                        message.ParseFromString(payload)
                        kind = message.WhichOneof('payload_variant')
                        if kind == 'config_complete_id' and message.config_complete_id == nonce:
                            verified_at, deadline = time.monotonic(), 0
                        elif kind == 'packet':
                            event = packet_from_proto(message.packet)
                            if event:
                                if len(queue) < 1000:
                                    queue.append(event)
                                else:
                                    dropped += 1
                except socket.timeout:
                    pass
                if deadline and time.monotonic() >= deadline:
                    raise TimeoutError('Local configuration exchange timed out')
        except (OSError, ValueError, DecodeError):
            if connection is not None:
                connection.close()
            connection, verified_at = None, 0
            retry_at = time.monotonic() + 10
        now = time.monotonic()
        try:
            if now >= health_at:
                ready = connection is not None and bool(verified_at) and now - verified_at < 30
                request(path, {'operation': 'service_health', 'name': 'meshtastic',
                               'ready': ready, 'detail': 'Local Meshtastic API verified' if ready
                               else 'Waiting for local Meshtastic API verification'})
                health_at = now + 5
            if queue:
                request(path, {'operation': 'publish_event', 'event': queue[0]})
                queue.pop(0)
            if dropped:
                request(path, {'operation': 'publish_event', 'event': {
                    'source': 'meshtastic', 'type': 'receiver.overflow', 'severity': 'warning',
                    'category': 'fault', 'data': {'summary': f'{dropped} messages lost while event storage was unavailable'}}})
                dropped = 0
        except (OSError, RuntimeError, ValueError):
            # Keep undelivered messages; lease expiry discloses collector interruption.
            time.sleep(1)
        if connection is None:
            time.sleep(.2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.home() / 'jetson-backpack-dev')
    serve(parser.parse_args().root)
