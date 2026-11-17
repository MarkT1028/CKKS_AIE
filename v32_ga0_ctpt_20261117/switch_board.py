"""Stage the compact or original Split BO image in the VEK280 slot 1."""
import argparse
import subprocess
from pathlib import Path
import run_board


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('variant', choices=('ctpt', 'splitbo'))
    parser.add_argument('action', choices=('check', 'arm'), default='check', nargs='?')
    args = parser.parse_args()
    variant = {'ctpt': run_board.VARIANT, 'splitbo': 'v32_native_splitbo_2_pipe'}[args.variant]
    board, _ = run_board.board_check()
    root = run_board.ROOT
    with board.lock():
        env = board.environment()
        if args.action == 'arm':
            for prefix in ('v32-ga0-full-active-', 'v32-ga-live-active-', 'v32-ga-resident-active-'):
                run_board.require(not Path('/run', prefix + env['boot_id']).exists(),
                                  'previous PL invocation was interrupted')
        subprocess.run(['sh', 'stage_variant_board.sh', variant, '--check'], cwd=root, check=True)
        if args.action == 'arm':
            subprocess.run(['sh', 'stage_variant_board.sh', variant], cwd=root, check=True)
            subprocess.run(['sh', 'prepare_variant_srst.sh', variant, '--check'], cwd=root, check=True)
            subprocess.run(['sh', 'prepare_variant_srst.sh', variant], cwd=root, check=True)


if __name__ == '__main__':
    main()
