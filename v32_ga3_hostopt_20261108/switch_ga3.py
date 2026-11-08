"""Explicit manual stage/check/arm, preserving stock image and second slot."""
import argparse, subprocess
import ga3_board as b
def main():
    p=argparse.ArgumentParser();p.add_argument('variant',choices=b.VARIANTS);p.add_argument('action',choices=['check','arm'],nargs='?',default='check');a=p.parse_args()
    b.board()
    with b.lock():
        b.code_check()
        def run(*args):subprocess.run(['sh',str(b.ROOT/args[0]),*args[1:]],cwd=b.ROOT,check=True)
        run('stage_variant_board.sh',a.variant,'--check')
        if a.action=='check':print('CHECK_ONLY: no boot files/registers/reboot request changed');return
        run('stage_variant_board.sh',a.variant)
        run('prepare_variant_srst.sh',a.variant,'--check')
        run('prepare_variant_srst.sh',a.variant)
        print('ARMED_ONLY: review successful output, then run sync && reboot yourself.')
if __name__=='__main__':main()
