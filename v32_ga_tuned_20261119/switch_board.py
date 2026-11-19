"""Check or arm an available sealed GA slot-1 image."""
import argparse
from pathlib import Path
import subprocess

import run_board
from ga_all_board import available_images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    aliases = available_images()
    parser.add_argument('variant', choices=aliases)
    parser.add_argument('action', choices=('check','arm'), default='check', nargs='?')
    args = parser.parse_args()
    variant = aliases[args.variant].variant
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
