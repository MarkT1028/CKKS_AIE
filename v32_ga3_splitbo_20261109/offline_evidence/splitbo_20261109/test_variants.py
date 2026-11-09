"""Deployed AXLF parsers, exact identity shims, and isolated boot staging."""
from pathlib import Path
import contextlib,hashlib,json,shutil,struct,subprocess,sys,tempfile,time
R=Path(__file__).resolve().parent;K=R.parents[1]/'board_packages/v32_ga3_splitbo_20261109';B=R/'build';T=B/('variants_'+str(time.time_ns()));T.mkdir()
sys.path.insert(0,str(K));import ga3_board as b;import switch_ga3 as s
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
cases=[]
for variant in b.VARIANTS:
    for profile in (('candidate',) if variant=='v32_native_splitbo_2_pipe' else ('baseline','candidate')):
        frozen=profile=='baseline';base=K/'frozen_compactio' if frozen else K
        native=variant!='v32_core_2_pipe';old='v32_native_pl_2_pipe' if native else variant
        config=K/'variants'/variant/'host'/f'identity_override_{profile}.hpp' if variant in ('v32_native_lazy8_2_pipe','v32_native_splitbo_2_pipe') else base/'variants'/old/'host/variant_config.hpp'
        src=T/f'{variant}_{profile}.cpp';exe=src.with_suffix('')
        src.write_text('#define CKKSMAC_PARSER_ONLY\n#include "'+str(config)+'"\n#define main hidden_original_main\n#include "'+str(base/'variants'/old/'host/timed_base.hpp')+'"\n#undef main\nint main(int argc,char**argv){try{require(argc==2,"metadata path");validate_boot_xclbin(argv[1]);return 0;}catch(const std::exception&e){std::cerr<<e.what()<<"\\n";return 1;}}\n')
        subprocess.run(['g++','-O2','-std=c++17','-pthread',src,'-o',exe],check=True)
        def call(path,label,expect):
            p=subprocess.run([exe,path],capture_output=True,text=True);assert (p.returncode==0)==expect,(label,p.stdout,p.stderr);cases.append(dict(variant=variant,profile=profile,label=label,expected_accept=expect,returncode=p.returncode))
        for other in b.VARIANTS:call(K/'variants'/other/'ckks_hw_boot.xclbin','identity_'+other,variant==other)
        blob=(K/'variants'/variant/'ckks_hw_boot.xclbin').read_bytes()
        for mode in ('truncated','bad_magic','action_mask','wrong_uuid','zero_sections','PDI','section_bounds','AIE_contract'):
            x=bytearray(blob)
            if mode=='truncated':x=x[:100]
            elif mode=='bad_magic':x[0]^=1
            elif mode=='action_mask':x[334]=1
            elif mode=='wrong_uuid':x[416]^=1
            elif mode=='zero_sections':struct.pack_into('<I',x,448,0)
            elif mode=='PDI':struct.pack_into('<I',x,456,18)
            elif mode=='section_bounds':struct.pack_into('<Q',x,480,len(x)+1)
            elif native:struct.pack_into('<I',x,456,25)
            else:
                for i in range(struct.unpack_from('<I',x,448)[0]):
                    if struct.unpack_from('<I',x,456+40*i)[0]==25:struct.pack_into('<I',x,456+40*i,11)
            bad=T/f'{variant}_{profile}_{mode}.xclbin';bad.write_bytes(x);call(bad,mode,False)

common=K/'perf2_boot_common.sh'
for variant in b.VARIANTS:
    p=subprocess.run(['sh','-c','. "$1"; perf2_root=$2; perf2_variant "$3"; perf2_hash_check "$perf2_candidate" "$perf2_candidate_sha"; printf "%s" "$perf2_uuid"','test',str(common),str(K),variant],capture_output=True,text=True,check=True)
    assert p.stdout==b.registry()[variant]['uuid']
for path in K.glob('*.sh'):subprocess.run(['sh','-n',path],check=True)
sd=T/'mock_sd';sd.mkdir();slot=sd/'boot0001.bin';stock=sd/'BOOT.BIN';slot2=sd/'boot0002.bin';slot.write_bytes(b'old mock slot');stock.write_bytes(b'stock mock');slot2.write_bytes(stock.read_bytes());stocksha=sha(stock)
def stage(source,before,after,ok):
    p=subprocess.run(['sh','-c','. "$1"; perf2_stage_files "$2" "$3" "$4" "$5"','test',str(common),str(sd),str(source),before,after],capture_output=True,text=True)
    assert (p.returncode==0)==ok,(p.stdout,p.stderr)
source=K/'variants/v32_native_splitbo_2_pipe/boot0001.bin';old=sha(slot);new=sha(source);stage(source,old,new,True)
assert sha(slot)==new and sha(sd/f'ckks_saved_SLOT1_{old[:16]}.bin')==old and sha(stock)==sha(slot2)==stocksha
before={p.name:sha(p) for p in sd.iterdir()};stage(source,new,'0'*64,False);assert before=={p.name:sha(p) for p in sd.iterdir()}
calls=[];b.board=lambda:calls.append('board');b.lock=contextlib.nullcontext;b.code_check=lambda:calls.append('code-check')
def command(args,**kw):calls.append(args[1:])
s.subprocess.run=command
for variant in b.VARIANTS:
    for action in ('check','arm'):
        calls.clear();sys.argv=['switch_ga3.py',variant,action];s.main()
        expected=['board','code-check',[str(K/'stage_variant_board.sh'),variant,'--check']]
        if action=='arm':expected.extend([[str(K/'stage_variant_board.sh'),variant],[str(K/'prepare_variant_srst.sh'),variant,'--check'],[str(K/'prepare_variant_srst.sh'),variant]])
        assert calls==expected,calls
b.write(B/'variant_verification.json',dict(status='PASS_FOUR_VARIANTS_EXACT_IDENTITIES_METADATA_AND_MOCK_STAGING',parser_cases=cases,actual_SD_changed=False,real_register_or_reboot=False))
print('PASS_VARIANT_PROTOCOLS',len(cases))
