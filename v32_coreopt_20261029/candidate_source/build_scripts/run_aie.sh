#!/usr/bin/env bash
set -euo pipefail
set +u
source /home/mark/AMDDesignTools/2025.2/Vitis/settings64.sh
set -u
export PATH=/home/mark/AMDDesignTools/2025.2/Vitis/aietools/bin:$PATH
root=/mnt/e/v32_gpu/v32_gpu/integration/v32_coreopt_20261029
exec python3 "$root/build_aie.py" "$@"
