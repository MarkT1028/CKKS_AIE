# 三方同平台 routed 資源

|版本|AIE compute|LUT|FF|DSP|RAMB36|RAMB18|BRAM36等效|
|---|---:|---:|---:|---:|---:|---:|---:|
|v32_core_2_pipe|2|35857|45748|334|24|2|25.0|
|v32_pure_pl_2_pipe|0|66979|58712|376|24|2|25.0|
|v32_native_pl_2_pipe|0|34031|45402|420|38|2|39.0|

全部為routed bd_wrapper，含平台與介面，PL225MHz。新純PL資源取自新實作，不沿用舊報表。板上速度及實際輸出原上下文續算均待測。

新native純PL的WNS為+0.488ns、WHS為+0.019ns，DRC error為0，保留286項warning checks；不宣稱零警告或實測Fmax。詳細routed與DRC報表均附於offline_evidence。
