"""Shared sealed board identity and input selection."""
import ipaddress
import os
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
VARIANT = 'v32_ga_dualmode_2_pipe'
HARDWARE = ROOT / 'variants' / VARIANT
XCLBIN = HARDWARE / 'ckks_hw_boot.xclbin'


def boot_uuid():
    result = (HARDWARE / 'EXPECTED_BOOT_UUID').read_text(encoding='ascii').strip()
    if not re.fullmatch(r'[0-9a-f]{32}', result):
        raise ValueError('invalid sealed GA boot UUID')
    return result


def input_source():
    address = os.environ.get('V32_GA_INPUT_IP')
    if not address:
        return 'sd'
    ipaddress.IPv4Address(address)
    port = os.environ.get('V32_GA_INPUT_PORT', '8407')
    key = os.environ.get('V32_GA_INPUT_KEY', '')
    if (not re.fullmatch(r'[0-9]{1,5}', port) or not 1 <= int(port) <= 65535
            or not re.fullmatch(r'[0-9a-f]{64}', key)):
        raise ValueError('invalid GA input port or 64-character sender key')
    return 'net'
