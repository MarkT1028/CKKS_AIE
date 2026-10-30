from pathlib import Path
import hashlib,json,shutil
R=Path(__file__).resolve().parent;P=R/'board_files'
def main():
    systems={
        'v32_diag_2_pipe':Path('/home/mark/v32_aie_20261027/hardware/systems/v32_diag_2_pipe'),
        'v32_core_2_pipe':Path('/home/mark/v32_coreopt_20261029/hardware/systems/v32_core_2_pipe')}
    for name in ('v32_aie_only_2_pipe','v32_reducer_only_2_pipe'):systems[name]=Path(json.loads((R/'evidence'/('hardware_'+name+'.json')).read_text())['build'])
    evidence=P/'offline_evidence/resource_matrix';evidence.mkdir(exist_ok=True);rows={}
    fields=('total_LUT','logic_LUT','LUTRAM','SRL','FF','RAMB36','RAMB18','URAM','DSP')
    for name,system in systems.items():
        report=system/'postcheck_utilization.rpt';text=report.read_text();line=next(x for x in text.splitlines() if x.startswith('| bd_wrapper '));values=[x.strip() for x in line.split('|')[1:-1]]
        assert values[:2]==['bd_wrapper','(top)'] and len(values[2:])==9
        row={k:int(v) for k,v in zip(fields,values[2:])};row['BRAM36_equivalent']=row['RAMB36']+row['RAMB18']/2;row['AIE']=2;row['PL_Hz']=225000000
        row['timing']=json.loads((system/'postcheck_signoff.json').read_text());row['utilization_sha256']=hashlib.sha256(report.read_bytes()).hexdigest();rows[name]=row
        shutil.copy2(report,evidence/(name+'_utilization.rpt'));shutil.copy2(system/'postcheck_signoff.json',evidence/(name+'_signoff.json'))
    out=dict(status='PASS_FOUR_ROUTED_RESOURCE_MATRIX',scope='Vivado routed top-level totals including common platform; BRAM in 36Kb equivalents; AIE count separately from retained AIE library mapping. Not measured power or performance.',variants=rows)
    (P/'RESOURCE_MATRIX.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
