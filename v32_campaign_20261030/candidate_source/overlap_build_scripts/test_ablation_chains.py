"""Recheck both missing cells with actual AIE output -> random-stall RTL."""
from pathlib import Path
import subprocess
R=Path(__file__).resolve().parent;PREVIOUS=R.parent/'v32_coreopt_20261029'
def main():
    for name,aie,reducer in (('aie_only','static','reducer_pipeline'),('reducer_only','baseline','reducer_forward')):
        source=(PREVIOUS/'test_chain.py').read_text()
        old="R=Path(__file__).resolve().parent;W=R.parents[1];B=Path('/home/mark/v32_coreopt_20261029/chain')"
        assert old in source
        source=source.replace(old,"R=Path('"+str(R)+"');W=R.parents[1];B=Path('/home/mark/v32_overlap_20261029/chain_"+name+"')")
        source=source.replace("R/'evidence/aie_static_real.json'","Path('"+str(PREVIOUS/'evidence'/('aie_'+aie+'_real.json'))+"')")
        source=source.replace('{R}/design/reducer_forward.cpp',str(PREVIOUS/'design'/(reducer+'.cpp'))).replace('{R}/design',str(PREVIOUS/'design'))
        source=source.replace("sha(R/'design/reducer_forward.cpp')","sha(Path('"+str(PREVIOUS/'design'/(reducer+'.cpp'))+"'))")
        source=source.replace('PASS_ACTUAL_AIE_OUTPUT_TO_NEW_REDUCER_CSIM_AND_RANDOM_STALL_RTL','PASS_ABLATION_ACTUAL_AIE_TO_RANDOM_STALL_REDUCER_RTL')
        for f in ('chain_rtl.json','chain_rtl_cosim.rpt','chain_tb.cpp'):source=source.replace("R/'evidence/"+f+"'","R/'evidence/"+name+'_'+f+"'")
        # Replacement paths above affect only evidence copies, not the real test bench.
        script=R/'build'/('chain_'+name+'.py');script.write_text(source)
        print('START_ABLATION_CHAIN',name,flush=True);subprocess.run(['python3',str(script)],check=True);print('PASS_ABLATION_CHAIN',name,flush=True)
if __name__=='__main__':main()
