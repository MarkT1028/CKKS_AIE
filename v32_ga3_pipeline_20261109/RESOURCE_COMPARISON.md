# 三種架構的 routed 總資源

|版本|AIE compute|LUT|FF|DSP|RAMB36|RAMB18|BRAM36等效|
|---|---:|---:|---:|---:|---:|---:|---:|
|v32_core_2_pipe|2|35857|45748|334|24|2|25.0|
|v32_native_pl_2_pipe|0|34031|45402|420|38|2|39.0|
|v32_native_lazy8_2_pipe|0|45796|73354|286|38|2|39.0|

全部取自完整 routed bd_wrapper，含同平台和介面，兩條管線、PL225MHz；不是 HLS 單 kernel 估計。新 lazy8 的板上速度與功耗仍待測。
新架構的 timing、route、DRC 與 HLS／RTL 證據見 offline_evidence/v32_native_lazy8_2_pipe。
