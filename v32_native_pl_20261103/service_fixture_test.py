"""Automatic2 requests to ONE board process; fixed public fixture, not live v32."""
from pathlib import Path
import json,os,sys
import compact_io as io,full_board as base,memory_admission,stream_board as s
def summarize(folder):
 folder=Path(folder);log=(folder/'service.log').read_text();io.need('STREAM_READY backend=XRT_AIE fixture_only=1' in log and 'STREAM_DONE request_1' in log and 'STREAM_DONE request_2' in log and 'STREAM_STOPPED' in log,'incomplete service protocol');setup=io.load(folder/'session/setup.json');io.need(setup['execution_backend']=='XRT_AIE' and setup['fixture_service'],'not real persistent board process');requests=[]
 for request,order in [('request_1',list(range(5,-1,-1))),('request_2',list(range(6)))]:
  root=folder/'session'/request;its=s.rows(root/'iterations.csv');gs=s.rows(root/'groups.csv');io.need(len(its)==2 and len(gs)==12 and all(int(x['verified_words'])==33030144 and int(x['warmup'])==0 for x in its),'service coverage');io.need([int(x['repetition']) for x in its]==[0,1] and [int(x['export_only']) for x in its]==[0,1] and [int(x['group']) for x in gs]==order*2,'service order/export')
  for rep,it in enumerate(its):
   group=[x for x in gs if int(x['repetition'])==rep];io.need(len(group)==6 and [int(x['ordinal']) for x in group]==list(range(6)) and all(int(x['verified_words'])==5505024 and int(x['warmup'])==0 and int(x['export_only'])==rep for x in group),'service group coverage/tags')
   for column,total in [('group_wall_ms','group_wall_sum_ms'),('pack_work_ms','pack_work_sum_ms'),('execute_envelope_sum_ms','execute_envelope_sum_ms'),('verify_work_ms','verify_work_sum_ms')]:s.near(sum(float(x[column]) for x in group),it[total])
   io.need(float(it['request_wall_ms'])+.01>=float(it['shared_validate_ms'])+float(it['group_wall_sum_ms']),'service shared work excluded')
  summary=io.load(root/'summary.json');io.need(summary['execution_backend']=='XRT_AIE','model not board');s.near(summary['request_wall_median_ms'],its[0]['request_wall_ms']);requests.append(dict(request=request,outputs=s.verify_outputs(root),traced_chunks=s.check_trace(root),summary=summary))
 command=io.load(folder/'service.command.json');io.need(command['returncode']==0 and command['pid']>0,'failed service process')
 return dict(status='PASS_TWO_PERSISTENT_FIXTURE_REQUESTS_PENDING_GROUND_RETURN',one_process_pid=command['pid'],requests=requests,scope='Same real fixture, two orders, one graph/kernel/BO/worker lifetime. No new live input transport or original v32 execution on remote Windows.')

def main():
 base.board()
 with base.device_lock():
  code=base.check(True);env=base.environment();io.need(env['boot_uuid']==base.UUID,'wrong firmware');admission=memory_admission.assess(env['meminfo'],os.sysconf('SC_PAGE_SIZE'));build=s.checked_build(code);folder=s.ROOT/('results_service_'+base.stamp());folder.mkdir();io.write_json(folder/'environment_before.json',env);io.write_json(folder/'run_identity.json',dict(**code,protocol='persistent_fixture_service_v1',build_identity=build,boot_id=env['boot_id'],boot_uuid=env['boot_uuid'],memory_admission=admission,fixture_only=True,original_v32_location='LOCAL_PC_NOT_REMOTE_WINDOWS'))
  try:
   s.command([s.ROOT/'bin/stream_host','--serve',s.ROOT/'variants/v32_core_2_pipe/ckks_hw_boot.xclbin',base.data(),folder/'session'],folder,'service',input_text='RUN request_1 1 0 descending\nRUN request_2 1 0 ascending\nQUIT\n')
   comparison=summarize(folder);after=base.environment();io.need(after['boot_id']==env['boot_id'] and after['boot_uuid']==base.UUID,'boot changed in service');io.write_json(folder/'environment_after.json',after);io.write_json(folder/'service_comparison.json',comparison);io.write_json(folder/'status.json',dict(status=comparison['status']));print('PASS_TWO_PERSISTENT_FIXTURE_REQUESTS',flush=True)
  except BaseException as e:io.write_json(folder/'environment_on_failure.json',base.environment());io.write_json(folder/'status.json',dict(status='FAILED_OR_INTERRUPTED_RETAIN_ALL',error=str(e)));raise
  finally:print('RESULTS='+str(folder),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:print('FAIL:',e,file=sys.stderr);sys.exit(1)
