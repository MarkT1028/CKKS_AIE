#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
python3 finish_board.py code-check
base=$(python3 finish_board.py base-path)
python3 -c 'import finish_board as f; prior,_,_=f.dependencies(); prior.board()'
mkdir -p bin
g++ -O3 -std=c++17 -pthread -I"$base" -I"$base/common" tests/sha_selftest.cpp -ldl -o bin/sha_selftest
bin/sha_selftest
g++ -O3 -std=c++17 -pthread -DCKKSMAC_PARSER_ONLY -I"$base" -I"$base/common" host/candidate.cpp -ldl -o bin/parser
data=$(python3 -c 'import finish_board as f; prior,_,_=f.dependencies(); print(prior.data())')
bin/parser --validate "$data"
g++ -O3 -std=c++17 -pthread -I"$base" -I"$base/common" -I/usr/include/xrt -include "$base/variants/v32_native_splitbo_2_pipe/host/identity_override_candidate.hpp" host/candidate.cpp -lxrt_coreutil -ldl -o bin/finish_host
bin/finish_host --crypto-check
python3 finish_board.py record-build
echo 'BUILD_READY_FINISHOPT: self-tests only; no PL execution, firmware write or reset.'
