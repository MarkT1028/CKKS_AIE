"""Select a sealed image and its matching board executables."""
import hashlib
import ipaddress
import os
from pathlib import Path
import re
from typing import NamedTuple


ROOT = Path(__file__).resolve().parents[1]
CTCT_LAYERS = ('ga3', 'ga6', 'ga9')
ALL_LAYERS = ('ga0', *CTCT_LAYERS)


class Image(NamedTuple):
    variant: str
    owner: str
    layers: tuple

    @property
    def markers(self):
        return ROOT / 'variants' / self.variant

    @property
    def xclbin(self):
        return ROOT.parent / self.owner / 'variants' / self.variant / 'ckks_hw_boot.xclbin'

    @property
    def uuid(self):
        value = (self.markers / 'EXPECTED_BOOT_UUID').read_text(encoding='ascii').strip()
        if not re.fullmatch(r'[0-9a-f]{32}', value):
            raise ValueError('invalid sealed GA boot UUID')
        return value

    def check_xclbin(self):
        expected = (self.markers / 'EXPECTED_XCLBIN_SHA256').read_text(encoding='ascii').strip()
        if self.xclbin.is_symlink() or hashlib.sha256(self.xclbin.read_bytes()).hexdigest() != expected:
            raise ValueError(f'{self.variant} xclbin differs from its sealed SHA256')


IMAGES = {
    'ctpt': Image('v32_ga0_ctpt_2_pipe', 'v32_ga0_ctpt_20261117', ('ga0',)),
    'splitbo': Image('v32_native_splitbo_2_pipe', 'v32_ga3_splitbo_20261109', CTCT_LAYERS),
    'dual3': Image('v32_ga_dualmode_2_pipe', 'v32_ga_all_20261117', ALL_LAYERS),
    'tuned': Image('v32_ga_tuned_2_pipe', 'v32_ga_tuned_20261119', ALL_LAYERS),
}


def available_images():
    return {name: image for name, image in IMAGES.items() if (image.markers/'EXPECTED_BOOT_UUID').is_file()}


def selected_image():
    label = os.environ.get('V32_GA_IMAGE')
    if label not in available_images():
        raise ValueError('select a sealed image through the top-level run_board.py')
    return label, IMAGES[label]


def boot_uuid():
    return selected_image()[1].uuid


def executable(component, name):
    return ROOT / component / 'bin' / selected_image()[0] / name


def read_ahead():
    value = os.environ.get('V32_GA_DISABLE_READ_AHEAD', '0')
    if value not in ('0', '1'):
        raise ValueError('invalid read-ahead setting')
    return value == '0'


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
