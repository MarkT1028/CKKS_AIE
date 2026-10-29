#!/bin/bash
set -eo pipefail
set +u
source /home/mark/AMDDesignTools/2025.2/Vitis/settings64.sh
set -u
python3 /mnt/e/v32_gpu/v32_gpu/integration/v32_coreopt_20261029/test_chain.py
