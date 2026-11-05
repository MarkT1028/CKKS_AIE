# Complete real g_a.3 comparison input data

Full captured real g_a.3 raw MAC workload: N=131072, active L=53, K=16; 16 output ciphertexts, 64 raw MAC groups, 4096 jobs, all coefficients and RNS towers. Public encrypted input/reference records only; no secret keys, contexts or evaluation keys are included.

Archive: v32_ga3_20261104_data.tar.gz

Archive bytes: 39334819787

Archive SHA256: f9d28c8e22ae5fcc3c96b5ee42babb64ab157cd0d09eff94b035d0ca84c095cf

Data manifest SHA256: d1bc302affb05586f8a9e875a12efc1b9db7f009a573a09986355b77402218a3

All 37 assets ga3_full_001.part through ga3_full_037.part are required. They reconstruct one immutable archive; the Git metadata contains exact per-asset sizes and SHA256 values. Use meta/download_release_data.ps1 after pulling the matching code.

Offline full integer replay and original-context return validation passed. This release does not assert any new g_a.3 board performance result, completed live layer acceleration, or that either hardware architecture has won.
