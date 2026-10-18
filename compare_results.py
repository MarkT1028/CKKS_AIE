"""Compare actual saved board results; never fills missing timings with estimates."""
from pathlib import Path
import argparse,csv,json,statistics,math,hashlib
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def main():
    a=argparse.ArgumentParser();a.add_argument('roots',nargs='+',type=Path);a.add_argument('--output',type=Path,default=Path('comparison.csv'));a.add_argument('--fixtures',type=Path,default=Path(__file__).resolve().parent/'fixtures');args=a.parse_args()
    results=[]
    for root in args.roots:
        for p in root.rglob('host/summary.csv'):
            c=read(p)[0];its=read(p.parent/'iterations.csv');measured=[r for r in its if r['warmup']=='0']
            assert c['K'] in ['1','16'] and c['mode'] in ['resident','transfer']
            assert all(all(r[k]==c[k] for k in ['variant','K','mode']) for r in its),'iteration and summary case identity differ'
            assert len(measured)==int(c['repetitions'])
            assert len(its)==int(c['repetitions'])+int(c['warmups'])
            assert [int(r['repetition']) for r in its]==list(range(len(its)))
            assert [int(r['warmup']) for r in its]==[1]*int(c['warmups'])+[0]*int(c['repetitions'])
            log=(p.parent.parent/'host.log').read_text()
            terminal='PASS DIAGNOSTIC_SINK_ONLY' if c['scope']=='diagnostic_sink_not_ckks_mac' else 'PASS FULL_MAC'
            assert terminal in log and 'FAIL' not in log,'case is not a fully passed run'
            if c['scope']=='raw_ckks_mac':
                expected=args.fixtures/('expected_raw.bin' if c['K']=='1' else 'expected_k16_raw.bin')
                actual=p.parent/'output_last.bin'
                assert expected.is_file() and actual.is_file(),'matching fixture and saved output required'
                digest=hashlib.sha256(expected.read_bytes()).hexdigest()
                assert hashlib.sha256(actual.read_bytes()).hexdigest()==digest,'full saved output differs from golden'
                fixture_manifest=(p.parent.parent.parent/'fixture_sha256.txt').read_text()
                recorded={Path(line.split(maxsplit=1)[1].lstrip('*')).name:line.split(maxsplit=1)[0] for line in fixture_manifest.splitlines() if line.strip()}
                inputname='inputs.bin' if c['K']=='1' else 'inputs_k16.bin'
                for name in [inputname,expected.name]:
                    ref=args.fixtures/name;assert ref.is_file(),'matching input and expected fixtures required'
                    assert recorded.get(name)==hashlib.sha256(ref.read_bytes()).hexdigest(),'reference fixture differs from recorded fixture hash'
            for key in ['execution_ms','transaction_ms','validation_ms']:
                s=sorted(float(r[key]) for r in measured);med=statistics.median(s)
                assert all(math.isfinite(value) and value>=0 for value in s),'invalid timing samples'
                assert abs(med-float(c[key.replace('_ms','_median_ms')]))<.0000011
            execution=sorted(float(r['execution_ms']) for r in measured)
            assert execution[0]>0
            assert abs(execution[math.ceil(.95*len(execution))-1]-float(c['execution_p95_ms']))<.0000011
            assert abs(execution[0]-float(c['execution_min_ms']))<.0000011 and abs(execution[-1]-float(c['execution_max_ms']))<.0000011
            c['source']=str(p);c['source_profile']=(p.parent.parent/'xrt.ini').read_text().replace('\n',';')
            results.append(c)
    if not results:raise SystemExit('No board measurements found; refusing to report a speedup')
    for r in results:
        if 'aie_profile=false' not in r['source_profile']:
            r['speedup_vs_baseline']='';continue
        base=[b for b in results if b['variant']=='baseline_1' and b['K']==r['K'] and b['mode']==r['mode'] and 'aie_profile=false' in b['source_profile']]
        r['speedup_vs_baseline']='' if len(base)!=1 or r['scope']!='raw_ckks_mac' else f"{float(base[0]['execution_median_ms'])/float(r['execution_median_ms']):.6f}"
    keys=list(dict.fromkeys(k for r in results for k in r))
    with args.output.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,keys);w.writeheader();w.writerows(results)
    print(json.dumps({'actual_board_cases':len(results),'comparison':str(args.output),'diagnostic_sink_excluded_from_ckks_speedup':True},ensure_ascii=False))
if __name__=='__main__':main()
