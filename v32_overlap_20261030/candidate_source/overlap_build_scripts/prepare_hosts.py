from pathlib import Path
import json,shutil
R=Path(__file__).resolve().parent;P=R/'board_files'
def main():
    variants=json.loads((P/'VARIANTS.json').read_text())
    for name,meta in variants.items():
        target=P/'variants'/name/'host';target.mkdir(exist_ok=True)
        for p in (P/'reference/host').iterdir():
            if p.is_file():shutil.copy2(p,target/p.name)
        s=(target/'variant_config.hpp').read_text().replace('6719127d5f785a7fa4fab0a9869d6ccd',meta['uuid']).replace('"v32_diag_2_pipe"','"'+name+'"')
        (target/'variant_config.hpp').write_text(s,encoding='utf-8',newline='\n')
        s=(P/'host/bo_host.cpp').read_text().replace('"../reference/host/perf_host.cpp"','"perf_host.cpp"').replace('"../reference/common/dataset_cache.hpp"','"../../../reference/common/dataset_cache.hpp"').replace('"../common/finish_overlap.hpp"','"../../../common/finish_overlap.hpp"')
        (target/'bo_host.cpp').write_text(s,encoding='utf-8',newline='\n')
    print('MATCHING_HOST_SOURCES',len(variants))
if __name__=='__main__':main()
