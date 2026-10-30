from pathlib import Path
R=Path(__file__).resolve().parent;P=R/'board_files'
def replace(text,a,b):
 assert text.count(a)==1,a[:80]
 return text.replace(a,b)
def main():
 p=P/'board_runner.py';t=p.read_text(encoding='utf-8')
 t=replace(t,'import record_io as records','import record_io as records\nfrom contextlib import contextmanager\n_DEVICE_LOCK=None\n_DEVICE_LOCK_PATH=None\n\n@contextmanager\ndef device_lock():\n    """One cross-package hardware lock, reentrant only within this process."""\n    global _DEVICE_LOCK,_DEVICE_LOCK_PATH\n    path=base()/".board.lock"\n    if _DEVICE_LOCK is not None:\n        require(_DEVICE_LOCK_PATH==path,"nested device lock changed dependency")\n        yield\n        return\n    with path.open("a") as lock:\n        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)\n        _DEVICE_LOCK,_DEVICE_LOCK_PATH=lock,path\n        try:yield\n        finally:_DEVICE_LOCK=None;_DEVICE_LOCK_PATH=None\n')
 t=replace(t,"status['status']=='OFFLINE_VERIFIED_READY_FOR_BOARD'","status['status']=='OFFLINE_VERIFIED_RESEARCH_CAMPAIGN_READY_FOR_BOARD'")
 t=replace(t,"status='PASS_OVERLAP_PACKAGE'","status='PASS_RESEARCH_CAMPAIGN_PACKAGE'")
 t=replace(t,'def run(kind,variant,reverse=False,campaign="host"):', 'def run(kind,variant,reverse=False,campaign="host",study_context=None):')
 t=replace(t,"    with (base()/'.board.lock').open('a') as lock:\n        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)","    with device_lock():")
 t=replace(t,"profiling=False,source_capture=","profiling=False,study_context=study_context,source_capture=")
 t=replace(t,"print('NEXT: python3 collect_results.py')","print('NEXT: sh run_study.sh status');return directory")
 p.write_text(t,encoding='utf-8',newline='\n')
 p=P/'cpu_diagnostics.py';t=p.read_text(encoding='utf-8')
 t=replace(t,"    with (r.base()/'.board.lock').open('a') as lock:\n        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)","    with r.device_lock():")
 t=replace(t,"        try:\n            samples=[];args=","        process=None;samples=[]\n        try:\n            args=")
 t=replace(t,"format(drift,'+.2f')+'%')","format(drift,'+.2f')+'%');return root")
 p.write_text(t,encoding='utf-8',newline='\n')
 p=P/'summarize_results.py';t=p.read_text(encoding='utf-8')
 t=replace(t,'def summarize(directory):','def summarize(directory,emit=True):')
 t=replace(t,"    (directory/'comparison.json').write_text(json.dumps(result,indent=2)+'\\n')","    if emit:(directory/'comparison.json').write_text(json.dumps(result,indent=2)+'\\n')")
 t=replace(t,"text='\\n'.join(lines)+'\\n';(directory/'comparison.txt').write_text(text);print(text,end='');return result","text='\\n'.join(lines)+'\\n'\n    if emit:(directory/'comparison.txt').write_text(text);print(text,end='')\n    return result")
 p.write_text(t,encoding='utf-8',newline='\n')
 # Ad-hoc raw runs remain possible for debugging, but never enroll into the study.
 (P/'run_round.sh').write_text('''#!/bin/sh
set -eu
echo 'Use sh run_study.sh next, host, ablation, or status for the controlled study.' >&2
exit 2
''',encoding='utf-8',newline='\n')
 (P/'run_study.sh').write_text('''#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$root/study.py" "${@:-next}"
''',encoding='utf-8',newline='\n')
 (P/'.gitignore').write_text('''bin/
__pycache__/
results_overlap_*/
results_cpu_diag_*/
study_runs/
study_summary.*
collected_study_*
collection_index_*
switch_logs/
.study.lock
.board.lock
!offline_evidence/
!offline_evidence/**
''',encoding='utf-8',newline='\n')
 print('CAMPAIGN_RUNNER_INSTRUMENTED_NO_ARITHMETIC_CHANGE')
if __name__=='__main__':main()
