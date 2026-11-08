"""Bounded, resumable, CPU-only lossless input preparation; original data is read-only."""
from pathlib import Path
import argparse,csv,hashlib,json,math,os,shutil,struct,subprocess,time
import ga3_board as b

def atomic(p,value):
    p=Path(p);tmp=p.with_name(p.name+'.new')
    b.need(not tmp.is_symlink(),'unsafe temporary metadata')
    with tmp.open('w',encoding='utf-8',newline='\n') as f:
        f.write(json.dumps(value,indent=2,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)

def identity(p):
    p=Path(p);b.need(p.is_file() and not p.is_symlink(),'missing/unsafe cache file '+str(p))
    s=p.stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

def digestmap(d):
    return dict((name,h) for h,name in (line.split('  ',1) for line in (d/'SHA256SUMS_DATA').read_text('ascii').splitlines()))

def plan(d,scope,budget):
    """Order: complete 16-window pilot, then weights, then remaining babies."""
    hashes=digestmap(d);jobs=list(csv.DictReader((d/'jobs.tsv').open(newline=''),delimiter='\t'))
    selected={};all_inputs={};pilot=set()
    for j in jobs:
        for field,kind in (('A',3),('B',4)):
            name=j[field];h=hashes[name]
            if h not in all_inputs:
                p=d/name;b.need(not p.is_symlink(),'source symlink')
                with p.open('rb') as f:
                    hdr=f.read(64);b.need(len(hdr)==64 and hdr[:8]==b'CKKSMAC1','source header')
                    version,k,n,l,pairs,components,layout,bits,r0,r1,words,r2=struct.unpack('<10I2Q',hdr[8:])
                    b.need(version==1 and k==kind and n==8192 and 1<=l<=16 and pairs==16 and components==2 and layout==1 and bits==64 and r0==r1==r2==0,'source dimensions')
                    qs=[struct.unpack('<3Q',f.read(24))[0] for _ in range(l)]
                b.need(all(2<=q<2**60 for q in qs) and words==n*l*pairs*2 and p.stat().st_size==64+24*l+8*words,'source length/moduli')
                size=128+64+24*l+pairs*(n*2//8)*sum(q.bit_length() for q in qs)
                all_inputs[h]=dict(original=name,canonical_sha256=h,kind=kind,logical_bytes=words*8,packed_bytes=size,widths=[q.bit_length() for q in qs])
            if int(j['coefficient_start']) in (0,122880) and int(j['output_ct']) in (0,15):pilot.add(h)
    sequence=sorted(all_inputs,key=lambda h:(h not in pilot,all_inputs[h]['kind']!=3,all_inputs[h]['original']))
    used=0
    for h in sequence:
        e=all_inputs[h]
        if scope=='pilot' and h not in pilot:continue
        if scope=='bounded' and used+e['packed_bytes']>budget:continue
        selected[h]=e;used+=e['packed_bytes']
    b.need(pilot<=set(selected),'cache budget too small for a complete pilot')
    return dict(format='GA3QPK01',scope=scope,source_manifest_sha256=b.sha(d/'SHA256SUMS_DATA'),
        entries=selected,pilot_fully_cached=True,all_input_digests=len(all_inputs),
        all_inputs_cached=len(selected)==len(all_inputs),packed_bytes=used,
        selected_logical_bytes=sum(e['logical_bytes'] for e in selected.values()),
        full_logical_input_bytes=sum(e['logical_bytes'] for e in all_inputs.values()),
        budget_bytes=budget if scope=='bounded' else None,
        scope_note='All raw MAC jobs remain covered. In a partial cache, UNDECLARED input digests deliberately use original raw files; a missing DECLARED cache entry is fatal.')

def path():
    value=os.environ.get('V32_GA3_CACHE');b.need(value,'Set V32_GA3_CACHE to the prepared pilot/full/bounded cache directory')
    p=Path(value);b.need(not p.is_symlink(),'cache root symlink');return p.resolve(strict=True)

def snapshot(cache,entries):
    b.need(not (cache/'inputs').is_symlink(),'cache inputs symlink')
    return {h:identity(cache/'inputs'/f'{h}.qpk') for h in entries}

def checked_identity():
    c=path();meta=b.load(c/'CACHE_COMPLETE.json');receipt=b.load(c/'CACHE_RECEIPT.json')
    p=b.load(c/'CACHE_PLAN.json');entries=p['entries']
    b.need(meta['status']=='PASS_LOSSLESS_INPUT_CACHE_READY' and p['format']=='GA3QPK01' and entries,'incomplete compact cache')
    b.need(meta['source_manifest_sha256']==b.sha(b.data()/'SHA256SUMS_DATA') and meta['plan_sha256']==b.sha(c/'CACHE_PLAN.json'),'wrong cache source/plan')
    b.need(receipt['index_sha256']==b.sha(c/'CACHE_INDEX.tsv')==meta['index_sha256'] and receipt['files']==snapshot(c,entries),'compact cache mutated; run compact_cache.py verify')
    rows=list(csv.DictReader((c/'CACHE_INDEX.tsv').open(newline=''),delimiter='\t'))
    b.need(set(rows[0])=={'canonical_sha256','packed_sha256','bytes'} and len(rows)==len(entries),'cache index columns/count')
    b.need({r['canonical_sha256'] for r in rows}==set(entries),'cache index differs from plan')
    for r in rows:
        h=r['canonical_sha256'];b.need(len(r['packed_sha256'])==64 and all(x in '0123456789abcdef' for x in r['packed_sha256']) and int(r['bytes'])==entries[h]['packed_bytes']==receipt['files'][h][2],'cache index size/digest')
    return dict(path=str(c),source_manifest_sha256=meta['source_manifest_sha256'],index_sha256=meta['index_sha256'],plan_sha256=meta['plan_sha256'],
        cached_inputs=len(entries),all_inputs_cached=p['all_inputs_cached'],packed_bytes=p['packed_bytes'],
        preparation_work_ms=meta['preparation_work_ms'],preparation_includes_read_encode_write_fsync_readback_full_hash=True,
        amortization='One-time preparation is additional cost. Never claim first-use acceleration using request-only timing.')

def prepare(scope,budget_gib,verify=False):
    start=time.monotonic()
    b.board();code=b.code_check();d=b.data();receipt=b.load(b.ROOT/'DATA_CHECK_RECEIPT.json')
    b.need(receipt['path']==str(d) and receipt['manifest_sha256']==b.sha(d/'SHA256SUMS_DATA') and receipt['files']==b.data_snapshot(d),'original data must pass check_package first')
    tool=b.ROOT/'bin/compact_tool';build=b.load(b.ROOT/'BUILD_IDENTITY.json');b.need(build['manifest_sha256']==code['manifest_sha256'] and build['compact_tool_sha256']==b.sha(tool),'rebuild compact tool')
    cache=Path(os.environ.get('V32_GA3_CACHE',str(b.ROOT.parent/f'v32_ga3_compact_cache_{scope}')))
    b.need(not cache.is_symlink(),'unsafe cache root');cache=cache.resolve()
    b.need(cache!=d and d not in cache.parents and cache not in d.parents,'cache must be separate from original data')
    with b.lock():
        t=start;p=plan(d,scope,int(budget_gib*2**30));cache.mkdir(exist_ok=True);(cache/'inputs').mkdir(exist_ok=True)
        b.need(not (cache/'inputs').is_symlink(),'unsafe cache inputs directory')
        if (cache/'CACHE_PLAN.json').exists():b.need(b.load(cache/'CACHE_PLAN.json')==p,'different cache plan; choose a new cache directory')
        else:atomic(cache/'CACHE_PLAN.json',p)
        state_path=cache/'PREPARATION_STATE.json';state=b.load(state_path) if state_path.exists() else dict(completed={},work_ms=0,plan_sha256=b.sha(cache/'CACHE_PLAN.json'))
        b.need(state['plan_sha256']==b.sha(cache/'CACHE_PLAN.json'),'cache checkpoint plan differs')
        records=state['completed'];existing=0
        for h,e in records.items():
            b.need(h in p['entries'],'completed cache entry not in plan')
            now=identity(cache/'inputs'/f'{h}.qpk')
            b.need(verify or now==e['identity'],'completed cache entry changed; run verify to recheck its actual decoded bytes')
            existing+=p['entries'][h]['packed_bytes']
        remaining=p['packed_bytes']-existing
        b.need(shutil.disk_usage(cache).free>remaining+2*2**30,'insufficient disk: keep 2 GiB reserve; original data was not deleted')
        print(json.dumps(dict(status='CACHE_PREPARATION_CPU_ONLY',scope=scope,inputs=len(p['entries']),packed_GiB=p['packed_bytes']/2**30,remaining_GiB=remaining/2**30,original_data_preserved=True)),flush=True)
        try:
            for i,(h,e) in enumerate(p['entries'].items()):
                dest=cache/'inputs'/f'{h}.qpk'
                if h in records and not verify:continue
                if h in records or dest.exists():
                    # Recover an interruption between atomic rename and the
                    # next checkpoint. Never trust or overwrite that file;
                    # decode/hash its actual bytes against the sealed source.
                    b.need(not dest.is_symlink(),'unsafe existing packed entry')
                    action='verify';target=dest
                else:
                    b.need(not dest.is_symlink(),'unsafe packed file')
                    target=dest.with_suffix('.qpk.partial')
                    # This one deterministic partial belongs solely to this
                    # derived-cache plan. It is not an original fixture file.
                    if target.exists():b.need(target.is_file() and not target.is_symlink(),'unsafe partial');target.unlink()
                    action='prepare'
                proc=subprocess.run([str(tool),action,str(d/e['original']),str(target),h],capture_output=True,text=True)
                b.need(proc.returncode==0,'cache tool failed: '+proc.stderr)
                result=json.loads(proc.stdout);b.need(result['status']=='PASS_LOSSLESS_INPUT_CACHE' and result['canonical_sha256']==h and result['logical_bytes']==e['logical_bytes'] and result['packed_bytes']==e['packed_bytes'],'cache tool evidence mismatch')
                if action=='prepare':os.replace(target,dest)
                records[h]=dict(packed_sha256=result['packed_sha256'],identity=identity(dest),canonical_sha256=h)
                elapsed=(time.monotonic()-t)*1000
                atomic(state_path,dict(completed=records,work_ms=state['work_ms']+elapsed,plan_sha256=state['plan_sha256']))
                print(f'CACHE_VERIFIED {i+1}/{len(p["entries"])} bytes={e["packed_bytes"]}',flush=True)
            b.need(receipt['files']==b.data_snapshot(d),'original data changed during preparation')
            lines=['canonical_sha256\tpacked_sha256\tbytes\n']+[f'{h}\t{records[h]["packed_sha256"]}\t{e["packed_bytes"]}\n' for h,e in sorted(p['entries'].items())]
            index=cache/'CACHE_INDEX.tsv';index.write_text(''.join(lines),encoding='ascii',newline='\n')
            work=state['work_ms']+(time.monotonic()-t)*1000
            atomic(state_path,dict(completed=records,work_ms=work,plan_sha256=state['plan_sha256']))
            atomic(cache/'CACHE_COMPLETE.json',dict(status='PASS_LOSSLESS_INPUT_CACHE_READY',source_manifest_sha256=p['source_manifest_sha256'],plan_sha256=b.sha(cache/'CACHE_PLAN.json'),index_sha256=b.sha(index),preparation_work_ms=work,scope=scope))
            atomic(cache/'CACHE_RECEIPT.json',dict(index_sha256=b.sha(index),files=snapshot(cache,p['entries'])))
            os.environ['V32_GA3_CACHE']=str(cache);result=checked_identity()
            atomic(b.ROOT/f'CACHE_PREPARATION_{b.stamp()}.json',result)
            print(json.dumps(dict(status='PASS_CACHE_READY',**result),indent=2))
        except BaseException:
            atomic(state_path,dict(completed=records,work_ms=state['work_ms']+(time.monotonic()-t)*1000,plan_sha256=state['plan_sha256']))
            raise

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['plan','prepare','verify','check']);p.add_argument('scope',nargs='?',default='pilot',choices=['pilot','bounded','full']);p.add_argument('--budget-gib',type=float,default=8);a=p.parse_args()
    b.need(math.isfinite(a.budget_gib) and 0<a.budget_gib<=64,'invalid cache budget')
    if a.action=='plan':
        t=time.monotonic();v=plan(b.data(),a.scope,int(a.budget_gib*2**30));v.pop('entries');v['plan_wall_ms']=(time.monotonic()-t)*1000;print(json.dumps(v,indent=2))
    elif a.action=='check':print(json.dumps(checked_identity(),indent=2))
    else:prepare(a.scope,a.budget_gib,verify=a.action=='verify')
if __name__=='__main__':
    try:main()
    except Exception as e:print('FAIL:',e);raise SystemExit(1)
