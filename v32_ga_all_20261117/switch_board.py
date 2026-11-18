"""Check or arm one of the three sealed GA slot-1 images."""
import argparse
from pathlib import Path
import subprocess

import run_board


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    aliases = dict(all=run_board.VARIANT, ctpt='v32_ga0_ctpt_2_pipe', splitbo='v32_native_splitbo_2_pipe')
    parser.add_argument('variant', choices=aliases)
    parser.add_argument('action', choices=('check','arm'), default='check', nargs='?')
    args = parser.parse_args()
    variant = aliases[args.variant]
    board = run_board.check()
    with board.lock():
        if args.action=='arm':
            boot = board.environment()['boot_id']
            for prefix in ('v32-ga0-full-active-', 'v32-ga-live-active-', 'v32-ga-resident-active-'):
                if Path('/run', prefix + boot).exists():
                    raise RuntimeError('previous PL invocation is marked active')
        subprocess.run(['sh','stage_variant_board.sh',variant,'--check'], cwd=run_board.ROOT, check=True)
        if args.action=='arm':
            subprocess.run(['sh','stage_variant_board.sh',variant], cwd=run_board.ROOT, check=True)
            subprocess.run(['sh','prepare_variant_srst.sh',variant,'--check'], cwd=run_board.ROOT, check=True)
            subprocess.run(['sh','prepare_variant_srst.sh',variant], cwd=run_board.ROOT, check=True)


if __name__=='__main__':
    main()
