#!/usr/bin/env bash
set -euo pipefail
set +u
source /home/mark/AMDDesignTools/2025.2/Vitis/settings64.sh
set -u
exec python3 /mnt/e/v32_gpu/v32_gpu/integration/v32_overlap_20261029/test_ablation_chains.py
