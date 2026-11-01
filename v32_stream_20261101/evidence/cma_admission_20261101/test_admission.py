"""Use the supplied real snapshot; XRT failure path is synthetic, never board proof."""
from pathlib import Path
from contextlib import nullcontext
import hashlib,json,sys,time
R=Path(__file__).resolve().parent;W=R.parents[1];P=R/'board_files';E=R/'evidence';E.mkdir(exist_ok=True);sys.path.insert(0,str(P));import full_board as b,memory_admission as m
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 src=Path('C:/Users/mark/.codex/attachments/0644a2fd-3150-4220-8025-98e61b4f8706/貼上的文字.txt');text=src.read_text(encoding='utf-8');start=text.index('{\n  "matching_variant"');snapshot=json.JSONDecoder().raw_decode(text[start:])[0]['environment'];facts=m.assess(snapshot['meminfo']);assert facts['CmaFree_kib']==125652 and facts['MemAvailable_kib']==3729820 and facts['CmaFree_below_old_threshold'] and facts['estimated_page_rounded_BO_bytes']==122961920
 b.io.write_json(E/'real_board_snapshot.json',snapshot);cases=['real125652KiB CmaFree passes snapshot only, actual XRT allocation pending']
 for label,mem,good in [('zero_free','MemAvailable: 3729820 kB\nCmaTotal: 524288 kB\nCmaFree: 0 kB',True),('low_RAM','MemAvailable: 1843199 kB\nCmaTotal: 524288 kB\nCmaFree: 524288 kB',False),('small_CMA','MemAvailable: 3729820 kB\nCmaTotal: 163839 kB\nCmaFree: 0 kB',False),('invalid_free','MemAvailable: 3729820 kB\nCmaTotal: 524288 kB\nCmaFree: 524289 kB',False),('missing_CMA','MemAvailable: 3729820 kB',False),('wrong_unit','MemAvailable: 3729820 MB\nCmaTotal: 524288 kB\nCmaFree: 0 kB',False)]:
  try:m.assess(mem);assert good,label
  except ValueError:assert not good,label
  cases.append(label)
 root=R/'build'/('synthetic_runtime_no_hardware_'+str(time.time_ns()));(root/'bin').mkdir(parents=True);b.ROOT=root;b.board=lambda:None;b.device_lock=lambda:nullcontext();b.environment=lambda:dict(snapshot);b.data=lambda:R/'NO_DATA_READ_IN_SYNTHETIC_FAILURE_TEST';b.check=lambda _:dict(manifest_sha256='synthetic-only',data={});b.stamp=lambda:'SYNTHETIC_NO_BOARD'
 if not hasattr(b.os,'sysconf'):b.os.sysconf=lambda name:4096
 hashes={}
 for name in ('full_host','full_cpu','full_parser'):p=root/'bin'/name;p.write_bytes(b'SYNTHETIC_NOT_AN_EXECUTABLE');hashes[name]=sha(p)
 b.io.write_json(root/'bin/build_identity.json',dict(code_manifest_sha256='synthetic-only',binaries=hashes));calls=[]
 def command(args,where,name):
  calls.append(name);(where/(name+'.log')).write_text('SYNTHETIC_NO_HARDWARE: '+name,encoding='utf-8')
  if name=='hardware':raise ValueError('SIMULATED_XRT_BO_ALLOCATION_FAILURE')
 b.command=command
 try:b.run('smoke');raise AssertionError('allocation error ignored')
 except ValueError as e:assert str(e)=='SIMULATED_XRT_BO_ALLOCATION_FAILURE'
 folder=next(root.glob('results_*'));assert calls==['cpu_before','hardware'];assert b.io.load(folder/'status.json')['status']=='FAILED_OR_INTERRUPTED_RETAIN_ALL';assert b.io.load(folder/'environment_on_failure.json')==snapshot and b.io.load(folder/'environment_before_hardware.json')==snapshot;assert b.io.load(folder/'run_identity.json')['memory_admission']['actual_BO_allocation']=='PENDING_XRT_SETUP'
 old=W/'board_packages/v32_full_hs4_20261031';preserved={}
 for p in old.rglob('*'):
  if p.is_file() and (p.suffix in ('.cpp','.hpp','.bin','.xclbin') or p.parent.name=='test_fixture' or p.name=='compact_io.py'):assert sha(p)==sha(P/p.relative_to(old));preserved[p.relative_to(old).as_posix()]=sha(p)
 result=dict(status='PASS_CMA_ADMISSION_AND_FATAL_ALLOCATION_FAILURE_RETENTION',user_snapshot=facts,cases=cases,synthetic_failure_does_not_run_cpu_after=True,failure_status_memory_snapshots_and_logs_retained=True,cache_or_sysctl_mutated=False,all_CPU_host_AIE_firmware_and_data_bytes_unchanged=preserved,board_tested=False,performance_change='NOT_CLAIMED',XRT_actual_allocation='PENDING_BOARD')
 b.io.write_json(E/'admission_tests.json',result);print(result['status'],flush=True)
if __name__=='__main__':main()
