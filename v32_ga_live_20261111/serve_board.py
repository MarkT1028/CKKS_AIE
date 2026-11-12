import contextlib
from pathlib import Path
import os
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'v32_ga3_splitbo_20261109'
PARENT_SHA = '9046e08779347d8b766f5341264ca71fa24914b0a50fb2cd988f59661b0fa2a7'
UUID = '9bee253b8f345f39bd9c18d612897ce3'


def checked_base():
    # The parent imports the existing board detection and hardware lock.
    import hashlib
    if hashlib.sha256((BASE / 'SHA256SUMS_PACKAGE').read_bytes()).hexdigest() != PARENT_SHA:
        raise RuntimeError('unexpected Split BO parent version')
    sys.path.insert(0, str(BASE))
    import ga3_board as board
    board.board()
    board.code_check()
    subprocess.run(['sha256sum', '-c', 'SHA256SUMS_PACKAGE'], cwd=ROOT, check=True, stdout=sys.stderr)
    return board


def stop_on_signal(number, _frame):
    raise SystemExit(128 + number)


def main():
    with contextlib.redirect_stdout(sys.stderr):
        board = checked_base()
        if sys.argv[1:] == ['check']:
            print('PASS_GA_LIVE_BOARD_PACKAGE')
            return 0
        if sys.argv[1:] not in (['serve'], ['ready']):
            raise ValueError('usage: serve_board.py check|ready|serve')
        subprocess.run(['sha256sum', '-c', 'bin/BUILD_SHA256'], cwd=ROOT, check=True, stdout=sys.stderr)
        with board.lock():
            env = board.environment()
            board.guard_recovery(env)
            if env['boot_uuid'] != UUID:
                raise RuntimeError('boot the Split BO pure-PL image first')
            marker = Path('/run/v32-ga-live-active-' + env['boot_id'])
            if marker.exists():
                raise RuntimeError('previous live PL invocation interrupted; reboot the board')
            if sys.argv[1:] == ['ready']:
                print('READY_GA_LIVE_BOARD')
                return 0
            for s in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
                signal.signal(s, stop_on_signal)
            command = [str(ROOT / 'bin/ga_server'), str(BASE / 'variants/v32_native_splitbo_2_pipe/ckks_hw_boot.xclbin'), str(marker)]
            child = None
            try:
                child = subprocess.Popen(command, start_new_session=True,
                                         env=dict(os.environ, XRT_INI_PATH=str(BASE / 'configs/baseline.ini')))
                return child.wait()
            finally:
                if child is not None and child.poll() is None:
                    board.stop_owned_child(child)
                if marker.exists():
                    board.write(BASE / 'RECOVERY_REQUIRED.json', dict(boot_id=env['boot_id'], reason='interrupted live g_a PL invocation'))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f'GA_BOARD_FAIL: {error}', file=sys.stderr)
        raise SystemExit(1)
