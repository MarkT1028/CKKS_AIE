#!/usr/bin/env python3
from study import export_summary,report
from study_tools import summarize
def main():
    data=summarize();export_summary(data);report(data)
if __name__=='__main__':main()
