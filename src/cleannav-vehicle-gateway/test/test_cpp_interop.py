"""Compile and exercise the standalone C++14 codec against shared vectors."""

import json
from dataclasses import asdict
from enum import Enum
from pathlib import Path
import shutil
import subprocess

import pytest

from cleannav_vehicle_gateway import protocol as cnvg


ROOT = Path(__file__).resolve().parents[3]
CPP_ROOT = ROOT / 'integration/cnvg_protocol'
VECTOR_FILE = CPP_ROOT / 'test_vectors/cnvg_v1_vectors.json'


@pytest.fixture(scope='module')
def cpp_cli(tmp_path_factory):
    compiler = shutil.which('g++')
    if compiler is None:
        pytest.fail('g++ is required for the C++14 protocol interoperability gate')
    output = tmp_path_factory.mktemp('cnvg-cpp') / 'protocol_cli'
    subprocess.run(
        [
            compiler,
            '-std=c++14',
            '-Wall',
            '-Wextra',
            '-I', str(CPP_ROOT / 'include'),
            '-I', str(ROOT / 'integration/legacy_autoware_gateway_ros1/include'),
            str(CPP_ROOT / 'src/protocol.cpp'),
            str(CPP_ROOT / 'test/cpp/protocol_cli.cpp'),
            '-o', str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output


def _fields(message):
    return {
        key: value.name if isinstance(value, Enum) else value
        for key, value in asdict(message).items()
    }


def test_python_cpp_interoperability_both_directions(cpp_cli):
    vectors = json.loads(VECTOR_FILE.read_text())
    emitted = subprocess.run(
        [str(cpp_cli), 'emit'], check=True, capture_output=True, text=True
    ).stdout
    cpp_hex = dict(line.split() for line in emitted.splitlines())

    for vector in vectors['vectors']:
        # C++ encoder -> Python decoder. C++ bytes must also match the golden file.
        assert cpp_hex[vector['name']] == vector['expected_hex']
        packet, message = cnvg.decode_message(bytes.fromhex(cpp_hex[vector['name']]))
        assert packet.message_type.name == vector['message_type']
        assert packet.sequence == vector['sequence']
        assert packet.timestamp_ms == vector['timestamp_ms']
        assert _fields(message) == vector['message']

        # Python encoder -> C++ decoder and byte-identical decode/re-encode.
        python_bytes = bytes.fromhex(vector['expected_hex'])
        result = subprocess.run(
            [str(cpp_cli), 'roundtrip', python_bytes.hex()],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
        assert int(result[0]) == cnvg.MessageType[vector['message_type']]
        assert int(result[1]) == vector['sequence']
        assert int(result[2]) == vector['timestamp_ms']
        assert result[3] == vector['expected_hex']


def test_cpp_codec_rejects_shared_malformed_vectors(cpp_cli):
    vectors = json.loads(VECTOR_FILE.read_text())
    for vector in vectors['malformed_vectors']:
        result = subprocess.run(
            [str(cpp_cli), 'roundtrip', vector['expected_hex']],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, vector['name']


def test_cpp_arbiter_sequence_and_mapping_core(tmp_path):
    compiler = shutil.which('g++')
    if compiler is None:
        pytest.fail('g++ is required for the C++14 command-arbiter gate')
    output = tmp_path / 'arbiter_test'
    subprocess.run(
        [
            compiler, '-std=c++14', '-Wall', '-Wextra',
            '-I', str(CPP_ROOT / 'include'),
            '-I', str(ROOT / 'integration/legacy_autoware_gateway_ros1/include'),
            str(CPP_ROOT / 'src/protocol.cpp'),
            str(CPP_ROOT / 'src/command_arbiter.cpp'),
            str(CPP_ROOT / 'test/cpp/arbiter_test.cpp'),
            '-o', str(output),
        ],
        check=True, capture_output=True, text=True,
    )
    result = subprocess.run([str(output)], check=True, capture_output=True, text=True)
    assert 'passed' in result.stdout
