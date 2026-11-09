from pathlib import Path
import json,os,shutil,struct,subprocess,time
R=Path(__file__).resolve().parent;B=R/'build';SOURCE=B/'synthetic';T=B/('loader_negative_'+str(time.time_ns()));T.mkdir();results=[]
cases=[('gold_first','record_2_16.bin','flip',64+24*16),('gold_last_L5','record_2_5.bin','flip',None),('baby_noncanonical','record_4_16.bin','noncanonical',64+24*16),('truncated_record','record_3_16.bin','truncate',None),('wrong_kind','record_4_16.bin','flip',12)]
for name,filename,action,offset in cases:
    d=T/name;shutil.copytree(SOURCE,d,copy_function=os.link);p=d/filename;payload=bytearray(p.read_bytes());p.unlink()
    if action=='truncate':payload=payload[:-8]
    elif action=='noncanonical':struct.pack_into('<Q',payload,offset,struct.unpack_from('<Q',payload,64)[0])
    else:payload[len(payload)-8 if offset is None else offset]^=1
    p.write_bytes(payload)
    call=[B/'final_model_2','unused',d,T/(name+'_result'),'smoke','1','0','descending','2']
    rc=subprocess.run(list(map(str,call)),capture_output=True,text=True,timeout=120)
    assert rc.returncode!=0,(name,rc.stdout,rc.stderr)
    results.append(dict(case=name,status='REJECTED',error=rc.stderr.strip()))
answer=dict(status='PASS_OPTIMIZED_LOADER_AND_FUSED_MERGE_CORRUPTION_REJECTION',cases=results,scope='Synthetic hardlink fixtures only; every mutation unlinks its own destination before writing. Real data untouched.')
(B/'loader_negative.json').write_text(json.dumps(answer,indent=2)+'\n');print(answer['status'])
