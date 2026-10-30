from pathlib import Path
R=Path(__file__).resolve().parent;P=R/'board_files'
def once(s,old,new):
    assert s.count(old)==1,(old[:120],s.count(old));return s.replace(old,new)
def main():
    s=(R/'reference/host/bo_host.cpp').read_text()
    s=once(s,'#include "../common/replay.hpp"','#include "../common/finish_overlap.hpp"')
    s=once(s,'xrt::graph& graph;CachedDataset& cache;bool mapped;','xrt::graph& graph;CachedDataset& cache;bool mapped,finish_overlap;')
    s=once(s,'bool use_maps,unsigned count,const fs::path& save):','bool use_maps,unsigned count,const fs::path& save,bool overlap_finish=false):')
    s=once(s,'graph(gr),cache(data),mapped(use_maps),merged','graph(gr),cache(data),mapped(use_maps),finish_overlap(overlap_finish),merged')
    s=once(s,'    void finish(unsigned index,unsigned bank,boexp::Frame& frame,Clock::time_point epoch){','''    void complete(unsigned,unsigned,boexp::Frame& frame,Clock::time_point epoch){
        frame.timed("status",-1,epoch,[&]{for(auto& kernel:kernels){require(kernel->reader.read_register(0x10)==0,"reader status");require(kernel->reducer.read_register(0x10)==0,"reducer status");}});
    }
    void finish(unsigned index,unsigned bank,boexp::Frame& frame,Clock::time_point epoch){''')
    needle='        frame.timed("status",-1,epoch,[&]{for(auto& kernel:kernels){require(kernel->reader.read_register(0x10)==0,"reader status");require(kernel->reducer.read_register(0x10)==0,"reducer status");}});'
    assert s.count(needle)==2
    start=s.index('    void finish(');s=s[:start]+s[start:].replace(needle,'        if(!finish_overlap)complete(index,bank,frame,epoch);',1)
    s=once(s,'mode=="copy_serial"||mode=="map_serial"||mode=="map_pingpong"','mode=="copy_serial"||mode=="map_serial"||mode=="map_pingpong"||mode=="map_finish_overlap"')
    s=once(s,'bool pipeline=mode=="map_pingpong";','bool overlap_finish=mode=="map_finish_overlap";bool pipeline=mode=="map_pingpong"||overlap_finish;')
    s=once(s,'pipeline?2:1,dir/"outputs");','pipeline?2:1,dir/"outputs",overlap_finish);')
    s=once(s,'auto result=boexp::run(backend,cache.chunks.size(),worker.get(),exporting);','auto result=overlap_finish?boexp::run_finish_overlap(backend,cache.chunks.size(),*worker,exporting):boexp::run(backend,cache.chunks.size(),worker.get(),exporting);')
    s=s.replace('copy_serial|map_serial|map_pingpong','copy_serial|map_serial|map_pingpong|map_finish_overlap')
    s=s.replace('host-observed preparation versus XRT run/wait intervals, not hardware DMA event proof','host-observed start-to-wait-return envelopes; finish-overlap also covers controller readback work from the previous chunk; not device event duration')
    s=s.replace('\\"stage_sum_is_not_wall_time\\":true','\\"stage_sum_is_not_wall_time\\":true,\\"timing_protocol\\":\\"v32_finish_overlap_v1\\"')
    (P/'host/bo_host.cpp').write_text(s,encoding='utf-8',newline='\n')
    print('NEXT_HOST_SOURCE_READY')
if __name__=='__main__':main()
