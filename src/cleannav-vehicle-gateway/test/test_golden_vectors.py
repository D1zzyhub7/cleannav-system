"""The checked-in JSON vectors are the shared CNVG wire-format truth."""

import json
from dataclasses import asdict
from enum import Enum
from pathlib import Path

import pytest

from cleannav_vehicle_gateway import protocol as cnvg


VECTOR_FILE = (
    Path(__file__).resolve().parents[3]
    / 'integration/cnvg_protocol/test_vectors/cnvg_v1_vectors.json'
)


def _load_vectors():
    return json.loads(VECTOR_FILE.read_text())


def _make_message(vector):
    name = vector['message_type']
    fields = dict(vector['message'])
    enum_fields = {
        'role': cnvg.PeerRole,
        'mode': cnvg.ControlMode,
        'gear': cnvg.Gear,
        'vehicle_mode': cnvg.VehicleMode,
        'state': cnvg.GatewayState,
    }
    for field_name, enum_type in enum_fields.items():
        if field_name in fields:
            fields[field_name] = enum_type[fields[field_name]]
    classes = {
        'HELLO': cnvg.Hello,
        'HEARTBEAT': cnvg.Heartbeat,
        'CONTROL_COMMAND': cnvg.ControlCommand,
        'VEHICLE_STATE': cnvg.VehicleState,
        'GATEWAY_STATUS': cnvg.GatewayStatus,
    }
    return classes[name](**fields)


def _normalized(message):
    values = asdict(message)
    return {
        key: value.name if isinstance(value, Enum) else value
        for key, value in values.items()
    }


def test_python_codec_matches_all_shared_golden_vectors():
    for vector in _load_vectors()['vectors']:
        message = _make_message(vector)
        wire = cnvg.encode_message(
            message,
            vector['sequence'],
            timestamp_ms=vector['timestamp_ms'],
        )
        assert wire.hex() == vector['expected_hex'], vector['name']
        packet, decoded = cnvg.decode_message(bytes.fromhex(vector['expected_hex']))
        assert packet.message_type.name == vector['message_type']
        assert packet.sequence == vector['sequence']
        assert packet.timestamp_ms == vector['timestamp_ms']
        assert _normalized(decoded) == vector['message'], vector['name']


@pytest.mark.parametrize(
    'vector', _load_vectors()['malformed_vectors'], ids=lambda item: item['name']
)
def test_python_codec_rejects_shared_malformed_vectors(vector):
    with pytest.raises(cnvg.ProtocolError, match=vector['reject_reason_contains']):
        cnvg.decode_message(bytes.fromhex(vector['expected_hex']))
