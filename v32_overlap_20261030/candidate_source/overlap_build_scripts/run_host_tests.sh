#!/usr/bin/env bash
set -euo pipefail
root=/mnt/e/v32_gpu/v32_gpu/integration/v32_overlap_20261029
cd "$root"
check=$(mktemp -d "$root/build/host_checks.XXXXXXXX")
for kind in zero max random;do
  build/finish_model "build/edge_fixtures/$kind" "$check/$kind" >"evidence/edge_$kind.log" 2>&1
  cat "evidence/edge_$kind.log"
done
for variant in $(python3 -c 'import json;print(" ".join(json.load(open("board_files/VARIANTS.json"))))');do
  source="board_files/variants/$variant/host/bo_host.cpp"
  g++ -O3 -std=c++17 -pthread -DDISABLE_ABI_CHECK -I/mnt/e/v32_gpu/v32_gpu/experiments/ckks_perf2_20261017/host_api_headers -fsyntax-only "$source" >"evidence/XRT_syntax_$variant.log" 2>&1
  g++ -O2 -std=c++17 -pthread -DCKKSMAC_PARSER_ONLY "$source" -o "$check/parser_$variant" >"evidence/parser_compile_$variant.log" 2>&1
  "$check/parser_$variant" --check-data /mnt/e/v32_gpu/v32_gpu/board_packages/v32_hs4_20261027/fixture >"evidence/full_partition_$variant.log" 2>&1
  cat "evidence/full_partition_$variant.log"
done
g++ -O3 -std=c++17 -pthread board_files/reference/cpu/cached_cpu.cpp -o "$check/cpu"
"$check/cpu" --self-test > evidence/CPU_selftest.log 2>&1
g++ -O3 -std=c++17 -pthread board_files/tests/fake_backend.cpp -o "$check/baseline_model"
"$check/baseline_model" board_files/test_fixture "$check/baseline" >evidence/baseline_model.log 2>&1
for f in board_files/*.sh;do sh -n "$f";done
python3 -m compileall -q board_files
echo PASS_HOST_COMPILE_PARTITIONS_EDGES_AND_BASELINE
