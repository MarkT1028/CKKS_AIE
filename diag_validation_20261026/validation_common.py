"""Shared, board-guarded helpers. No firmware programming or automatic reboot."""
from pathlib import Path,PurePosixPath
import hashlib,json,os,re,sys
ROOT=Path(__file__).resolve().parent
COMPARISON=ROOT/'comparison'
sys.path.insert(0,str(COMPARISON))
import board_experiment as formal
from controlled_board import BoardLock,Telemetry,environment,logged,write_json
sha,require,stamp,read=formal.sha,formal.require,formal.stamp,formal.read
snapshot,boot_uuid,board_check=formal.snapshot,formal.boot_uuid,formal.board_check
FLAGS=formal.FLAGS
VARIANTS=formal.VARIANTS
FORMAL_SHA='e8eb79f26795ada7523163e6a22efa51905cd0a1f61d01195c399cc1dbae27e9'
def fixtures(k):
    return (COMPARISON/'fixtures'/('inputs.bin' if k==1 else 'inputs_k16.bin'),COMPARISON/'fixtures'/('expected_raw.bin' if k==1 else 'expected_k16_raw.bin'))
def check_package():
    for p in ROOT.rglob('*'):
        require(p.name.lower() not in {'secret_key.bin','eval_mult_keys.bin','context.bin'},'Private fixture file found in board package')
    seen=set()
    for line in (ROOT/'SHA256SUMS_PACKAGE').read_text(encoding='utf-8').splitlines():
        m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line);require(m is not None,'Invalid manifest line')
        rel=PurePosixPath(m[2]);require(not rel.is_absolute() and '..' not in rel.parts and m[2] not in seen,'Unsafe/duplicate manifest path')
        require('private' not in rel.parts and not any(w in rel.name.lower() for w in ['secret_key','eval_mult_keys']),'Private material forbidden in board package')
        path=ROOT.joinpath(*rel.parts);require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(ROOT.resolve()),'Missing/unsafe file: '+m[2])
        require(sha(path)==m[1],'SHA mismatch: '+m[2]);seen.add(m[2])
    require(sha(COMPARISON/'SHA256SUMS_PACKAGE')==FORMAL_SHA,'Original formal package changed')
    child=formal.check_package()
    require(child['manifest_sha256']==FORMAL_SHA,'Formal package identity mismatch')
    original=(COMPARISON/'cpu/cpu_bench.cpp').read_text(encoding='utf-8')
    require((ROOT/'diagnostics/cpu_reference.inc').read_text(encoding='utf-8')==original[:original.index('int main(int argc,char** argv)')],'CPU reference implementation changed')
    for name in ['variant_config.hpp','timed_base.hpp','expected_reader.hpp']:
        require(sha(ROOT/'diagnostics/parser'/name)==sha(COMPARISON/'cpu/parser'/name),'CPU parser changed')
    require(sha(ROOT/'profile_host/variant_config.hpp')==sha(COMPARISON/'variants/diag_2_pipe/host/variant_config.hpp'),'Profile variant config changed')
    return {'status':'PASS_VALIDATION_PACKAGE','files':len(seen),'manifest_sha256':sha(ROOT/'SHA256SUMS_PACKAGE'),'formal_package_manifest_sha256':FORMAL_SHA,'firmware_changed':False}
def binary_record(name):
    path=ROOT/'bin'/name;record=json.loads((ROOT/'bin'/(name+'.build.json')).read_text())
    require(sha(path)==record['binary_sha256'],'Binary changed: '+name)
    require(record['architecture']=='aarch64' and record['flags']==FLAGS,'Not a matching ARM build')
    require(record['package_manifest_sha256']==sha(ROOT/'SHA256SUMS_PACKAGE'),'Stale diagnostic build')
    for relative,digest in record['source_files'].items():require(sha(ROOT/relative)==digest,'Build source changed: '+relative)
    return record
