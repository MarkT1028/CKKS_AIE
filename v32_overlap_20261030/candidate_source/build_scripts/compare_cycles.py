"""Summarize simulator time stamps; these are NOT board measurements."""
from pathlib import Path
import json,re,statistics
R=Path(__file__).resolve().parent
B=Path('/home/mark/v32_coreopt_20261029')
def timing(path):
    factors={'ps':.001,'ns':1.,'us':1000.,'ms':1000000.}
    stamps=[float(v)*factors[u] for v,u in re.findall(r'^T\s+([0-9.eE+-]+)\s+(ps|ns|us|ms)\s*$',path.read_text(),re.M)]
    starts=stamps[::112]
    intervals=[b-a for a,b in zip(starts,starts[1:])]
    # Keep every interval, explicitly report warm-start and steady statistics.
    steady=intervals[4:]
    return dict(beats=len(stamps),complete_frames=len(stamps)//112,first_beat_ns=stamps[0],last_beat_ns=stamps[-1],frame_start_intervals_ns=intervals,steady_excludes_first_intervals=4,steady_median_ns=statistics.median(steady),steady_min_ns=min(steady),steady_max_ns=max(steady))
def main():
    facts=dict(scope='cycle-accurate AIE graph simulation with PLIO 225MHz; independent of PL reducer and DDR; NOT board performance',aie={})
    for variant in ('baseline','static'):
        facts['aie'][variant]=[timing(B/f'aie/{variant}_real/hw/aiesimulator_output/data/partials{i}.txt') for i in range(2)]
    a=statistics.median(x['steady_median_ns'] for x in facts['aie']['baseline'])
    b=statistics.median(x['steady_median_ns'] for x in facts['aie']['static'])
    facts.update(aie_sim_interval_reduction_percent=100*(1-b/a),aie_sim_interval_speedup=a/b,board_performance='PENDING')
    (R/'evidence/cycle_comparison.json').write_text(json.dumps(facts,indent=2)+'\n')
    print(json.dumps({k:v for k,v in facts.items() if k!='aie'},indent=2))
    for variant,lanes in facts['aie'].items():
        print(variant,[(x['complete_frames'],x['steady_median_ns'],x['steady_max_ns']) for x in lanes])
if __name__=='__main__':main()
