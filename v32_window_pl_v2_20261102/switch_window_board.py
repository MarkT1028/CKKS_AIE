"""Manual check/arm only. Share the original experiment lock; never reboot."""
import argparse,subprocess
import full_board as base,window_board as wb
def switch(variant,action):
 if variant not in ('v32_core_2_pipe','v32_pure_pl_2_pipe') or action not in ('check','arm'):raise ValueError('invalid switch variant/action')
 base.board()
 with base.device_lock():
  wb.check()
  def call(script,*args):subprocess.run(['sh',str(wb.ROOT/script),*args],cwd=wb.ROOT,check=True)
  call('stage_variant_board.sh',variant,'--check')
  if action=='check':print('CHECK_ONLY: no boot files, request or registers changed');return
  call('stage_variant_board.sh',variant)
  call('prepare_variant_srst.sh',variant,'--check')
  call('prepare_variant_srst.sh',variant)
  print('ARMED_ONLY: review successful output, then run sync && reboot yourself. No automatic reboot.')
def main():
 p=argparse.ArgumentParser();p.add_argument('variant',choices=['v32_core_2_pipe','v32_pure_pl_2_pipe']);p.add_argument('action',choices=['check','arm'],nargs='?',default='check');a=p.parse_args();switch(a.variant,a.action)
if __name__=='__main__':main()
