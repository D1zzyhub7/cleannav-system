#!/usr/bin/env python3
"""Replay CNVG vectors or binary captures to a local UDP test endpoint only."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/cleannav-vehicle-gateway'))

from cleannav_vehicle_gateway.replay import parse_datagram_blob, replay_datagrams


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--hex', help='one CNVG datagram as hexadecimal')
    source.add_argument('--file', type=Path, help='binary datagram or framed capture')
    parser.add_argument('--target', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=39182)
    parser.add_argument('--duplicate', action='store_true')
    parser.add_argument('--out-of-order', action='store_true')
    parser.add_argument('--corrupt-byte', type=int, metavar='OFFSET')
    parser.add_argument('--delay-ms', type=int, default=0)
    parser.add_argument('--stale-session-id', type=lambda value: int(value, 0))
    args = parser.parse_args()
    try:
        blob = bytes.fromhex(args.hex) if args.hex is not None else args.file.read_bytes()
        datagrams = parse_datagram_blob(blob)
        sent = replay_datagrams(
            datagrams,
            target_ip=args.target,
            target_port=args.port,
            duplicate=args.duplicate,
            out_of_order=args.out_of_order,
            corrupt_byte=args.corrupt_byte,
            delay_ms=args.delay_ms,
            stale_session_id=args.stale_session_id,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f'replayed {sent} datagram(s) to 127.0.0.1:{args.port}')


if __name__ == '__main__':
    main()
