#!/usr/bin/env python3
"""Read-only observations around the UNCHANGED cached CPU reference.
Diagnostic sampling is separate from the primary hardware/CPU comparison.
"""
from pathlib import Path
import argparse,csv,fcntl,json,os,shutil,signal,statistics,subprocess,time
import board_runner as r
R=Path(__file__).resolve().parent
def task_sample(pid):
    values=[]
    for p in Path(f'/proc/{pid}/task').glob('*/stat'):
        process=None;samples=[]
        try:
            text=p.read_text();f=text[text.rfind(')')+2:].split();status=r.read(p.with_name('status')) or ''
            values.append(dict(tid=int(p.parent.name),state=f[0],minor_faults=int(f[7]),major_faults=int(f[9]),user_ticks=int(f[11]),system_ticks=int(f[12]),last_cpu=int(f[36]),status_context_switches=[s for s in status.splitlines() if 'ctxt_switches:' in s]))
        except (OSError,ValueError,IndexError):continue
    return values
def main(perf=False):
    identity=r.check();r.board();build=json.loads((R/'bin/build_identity.json').read_text())
    r.require(build['package_manifest_sha256']==identity['manifest_sha256'],'rebuild required')
    cpu=R/'bin/cached_cpu';r.require(r.records.sha(cpu)==build['binaries']['cached_cpu'],'CPU binary changed')
    with r.device_lock():
        active=sorted(os.sched_getaffinity(0));r.require(len(active)>=2,'need two CPU cores');os.sched_setaffinity(0,set(active[:2]))
        root=R/('results_cpu_diag_'+r.stamp());root.mkdir();r.write(root/'environment_before.json',r.environment())
        r.write(root/'identity.json',dict(**identity,cpu_sha256=r.records.sha(cpu),boot_id=r.environment()['boot_id'],diagnostic_only=True,formal_CPU_source_changed=False,sampling_ms=50,clock_ticks=os.sysconf('SC_CLK_TCK'),perf_requested=perf))
        process=None;samples=[]
        try:
            args=[str(cpu),str(r.base()/'fixture'),str(root/'cpu'), '12','2','2','nosave']
            with (root/'cpu.log').open('w') as log:
                process=subprocess.Popen(args,cwd=R,stdout=log,stderr=subprocess.STDOUT)
                while process.poll() is None:
                    samples.append(dict(monotonic=time.monotonic(),tasks=task_sample(process.pid),loadavg=r.read('/proc/loadavg'),meminfo=r.read('/proc/meminfo'),cpu_policy=r.environment()['cpu_policy']))
                    time.sleep(.05)
                code=process.wait()
            r.write(root/'task_samples.json',samples);r.require(code==0,'CPU diagnostic arithmetic run failed')
            with (root/'cpu/iterations.csv').open(newline='') as f:rows=list(csv.DictReader(f))
            measured=[float(x['compute_sum_ms']) for x in rows if x['warmup']=='0'];r.require(len(measured)==12,'CPU A/A counts')
            before=statistics.median(measured[:6]);after=statistics.median(measured[6:]);drift=(after/before-1)*100
            if perf:
                exe=shutil.which('perf')
                if exe:
                    args=[exe,'stat','-x,','-e','task-clock,cycles,instructions,cache-references,cache-misses,context-switches,cpu-migrations','--',str(cpu),str(r.base()/'fixture'),str(root/'perf_cpu'),'1','0','2','nosave']
                    try:
                        with (root/'perf.log').open('w') as log:
                            pmu=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                            try:code=pmu.wait(timeout=120)
                            except BaseException:
                                if pmu.poll() is None:
                                    try:os.killpg(pmu.pid,signal.SIGKILL)
                                    except ProcessLookupError:pass
                                pmu.wait();raise
                        r.write(root/'perf_status.json',dict(status='CAPTURED_REQUIRES_COUNTER_INSPECTION' if code==0 else 'UNAVAILABLE_OR_FAILED',exit_code=code,scope='whole extra CPU process including admission, setup, compute and validation; not compute-only counters',not_part_of_primary_comparison=True))
                    except subprocess.TimeoutExpired:r.write(root/'perf_status.json',dict(status='TIMED_OUT',not_part_of_primary_comparison=True))
                else:r.write(root/'perf_status.json',dict(status='PERF_NOT_INSTALLED',not_part_of_primary_comparison=True))
            r.write(root/'environment_after.json',r.environment());r.write(root/'status.json',dict(status='PASS_CPU_DIAGNOSTIC',same_process_fixed_cached_data=True,measured=12,compute_first6_median_ms=before,compute_last6_median_ms=after,drift_percent=drift,review=abs(drift)>5,all_formal_compute_samples_ms=measured,scope='diagnostic sampling overhead present; do not substitute for the adjacent primary CPU comparison; last_cpu is not a migration counter; scaling_cur_freq is a reported value'))
            print('CPU_DIAGNOSTIC_RESULTS='+str(root));print('CPU same-process A/A drift='+format(drift,'+.2f')+'%');return root
        except BaseException as exc:
            if process is not None and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            r.write(root/'task_samples.json',samples)
            r.write(root/'status.json',dict(status='FAILED_OR_INTERRUPTED',error=repr(exc)));raise
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--perf',action='store_true');a=p.parse_args();main(a.perf)
