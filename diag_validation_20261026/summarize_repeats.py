#!/usr/bin/env python3
"""Use the unchanged formal analyzer for original A1/B1 and new A2/B2 paths."""
import argparse,sys
import validation_common as v
from summarize_controlled import summarize
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('results',nargs='+');p.add_argument('--out');a=p.parse_args()
    try:v.check_package();summarize(a.results,a.out)
    except Exception as e:print('FAIL: '+str(e),file=sys.stderr);sys.exit(1)
