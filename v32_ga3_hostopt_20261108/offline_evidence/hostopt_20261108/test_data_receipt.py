from pathlib import Path
import hashlib,importlib.util,json,time
R=Path(__file__).resolve().parent;K=R.parents[1]/'board_packages/v32_ga3_hostopt_20261108'
T=R/'build'/('receipt_'+str(time.time_ns()));T.mkdir();d=T/'data';d.mkdir();new=T/'new';new.mkdir();old=T/'v32_ga3_20261104';old.mkdir()
spec=importlib.util.spec_from_file_location('receipt_test_control',K/'ga3_board.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
b.ROOT=new;b.code_check=lambda:dict(files=0,manifest_sha256='synthetic');b.data=lambda:d
(d/'input.bin').write_bytes(b'immutable test fixture');digest=hashlib.sha256((d/'input.bin').read_bytes()).hexdigest();(d/'SHA256SUMS_DATA').write_text(digest+'  input.bin\n')
ms=b.sha(d/'SHA256SUMS_DATA');(new/'DATA_PROVENANCE.json').write_text(json.dumps(dict(manifest_sha256=ms)))
b.write(old/'DATA_CHECK_RECEIPT.json',dict(path=str(d),manifest_sha256=ms,files=b.data_snapshot(d)))
s=b.check();assert s['data']['verification']=='PRIOR_FULL_SHA256_CHECK_WITH_IDENTICAL_FILE_IDENTITY_SNAPSHOT'
(d/'input.bin').write_bytes(b'mutated fixture')
try:b.check()
except ValueError as e:assert 'hash mismatch' in str(e)
else:raise AssertionError('mutated data reused prior receipt')
result=dict(status='PASS_PRIOR_RECEIPT_METADATA_REUSE_AND_MUTATION_REJECTION',synthetic_only=True)
(R/'build/receipt_verification.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
