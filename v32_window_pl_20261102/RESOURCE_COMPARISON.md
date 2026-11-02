# 雙 AIE／純 PL：實際佈線後總資源

|版本|AIE 運算核心|LUT|FF|DSP|RAMB36|RAMB18|BRAM36 等效|
|---|---:|---:|---:|---:|---:|---:|---:|
|v32_core_2_pipe|2|35857|45748|334|24|2|25|
|v32_pure_pl_2_pipe|0|66979|58712|376|24|2|25|

範圍是 routed bd_wrapper 全系統，含共同平台與介面；兩版 PL 目標皆為225MHz。資源數不是速度證明，實際 request/export 時間待板測。純 PL 是兩條相同 reader→精確7對角和→reducer 管線，沒有 AIE 運算；不是宣稱所有純 PL 架構中的最優解。
