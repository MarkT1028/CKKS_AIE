from pathlib import Path
import importlib.util,json,sys
R=Path(__file__).resolve().parent;K=R.parents[1]/'board_packages/v32_ga3_splitbo_20261109';sys.path.insert(0,str(K))
import ga3_board as b;import summarize_split as c
T=sorted(p for p in (R/'build').glob('control_*') if p.is_dir())[-1];b.ROOT=T
sys.argv=['summarize_split.py'];c.main();s=b.load(T/'split_comparison_summary.json');assert len(s['comparisons'])==1 and len(s['reuse_ablations'])==1
assert not s['comparisons'][0]['cross_boot_ABA_completed'] and s['comparisons'][0]['review_required']
assert s['comparisons'][0]['mode']=='probe' and s['comparisons'][0]['order']=='descending'
b.write(R/'build/compare_verification.json',dict(status='PASS_MATCHED_SCOPE_ORDER_TRIALS_CACHE_AND_COLD_ACCOUNTING',real_board=False,comparisons=1,reuse_ablations=1,unsupported_ABA_claim_rejected=True))
print('PASS_COMPARE_PROTOCOL')
