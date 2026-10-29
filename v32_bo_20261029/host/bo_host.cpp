#define PERF_HOST_NO_MAIN
#include "../reference/host/perf_host.cpp"
#include "../reference/common/dataset_cache.hpp"
#include "../common/replay.hpp"

namespace {
void check_data(const fs::path& root){
    CachedDataset cache(root);const auto& first=cache.chunks.front().input;
    std::array<std::vector<uint64_t>,2> mapped;for(auto& p:mapped)p.resize(first.words.size()/2);
    InputCase old;std::vector<uint64_t> out(first.output_words());unsigned checked=0;
    for(const auto& chunk:cache.chunks){for(unsigned lane=0;lane<2;++lane){
        fill_shard_block(chunk.input,lane,old);boexp::split_to(chunk.input,lane,mapped[lane].data(),mapped[lane].size());
        require(old.words==mapped[lane],"mapped split differs from frozen block split");
        std::vector<uint64_t> partial(old.output_words());
        for(unsigned t=0;t<chunk.input.l;++t)std::copy_n(chunk.expected.data()+(size_t(t)*chunk.input.n+lane*old.n)*3,old.n*3,partial.data()+size_t(t)*old.n*3);
        boexp::merge_from(chunk.input,lane,partial.data(),partial.size(),out);
    }compare(out,chunk.expected,0);++checked;}
    std::cout<<"PASS ALL_MAPPED_SPLITS_AND_MERGES chunks="<<checked<<" raw_words="<<cache.golden_bytes/8<<'\n';
}
#ifndef CKKSMAC_PARSER_ONLY
struct Kernels {
    xrt::kernel reader,reducer;
    Kernels(const xrt::device& device,const xrt::uuid& uuid,unsigned lane):
      reader(device,uuid,"ct_reader:{ct_reader_"+std::to_string(lane+1)+"}",xrt::kernel::cu_access_mode::exclusive),
      reducer(device,uuid,"ct_reduce_accum:{ct_reduce_accum_"+std::to_string(lane+1)+"}",xrt::kernel::cu_access_mode::exclusive){}
};
struct Buffers {
    InputCase shape;std::vector<uint64_t> host_output;
    xrt::bo input,output,parameters;xrt::run reader,reducer;
    uint64_t *mapped_input=nullptr,*mapped_output=nullptr;
    Buffers(const xrt::device& device,Kernels& kernel,const InputCase& full,bool mapped):
      input(device,full.words.size()/2*8,kernel.reader.group_id(0)),output(device,full.output_words()/2*8,kernel.reducer.group_id(1)),
      parameters(device,full.l*32,kernel.reducer.group_id(2)),reader(kernel.reader),reducer(kernel.reducer){
        shape.n=full.n/2;shape.l=full.l;shape.k=full.k;shape.parameters=full.parameters;
        if(mapped){mapped_input=input.map<uint64_t*>();mapped_output=output.map<uint64_t*>();require(mapped_input&&mapped_output,"BO mapping failed");}
        else{shape.words.resize(full.words.size()/2);host_output.resize(shape.output_words());}
        reader.set_arg(0,input);reader.set_arg(3,shape.n);reader.set_arg(4,shape.l);reader.set_arg(5,shape.k);
        reducer.set_arg(1,output);reducer.set_arg(2,parameters);reducer.set_arg(3,shape.n);reducer.set_arg(4,shape.l);reducer.set_arg(5,shape.k);
    }
};
struct Bank {std::array<std::unique_ptr<Buffers>,2> lanes;};
class XrtBackend {
    xrt::graph& graph;CachedDataset& cache;bool mapped;
    std::array<std::unique_ptr<Kernels>,2> kernels;
    std::vector<std::unique_ptr<Bank>> banks;
    std::vector<uint64_t> merged;fs::path output_dir;
    std::chrono::steady_clock::time_point deadline;
public:
    XrtBackend(const xrt::device& device,const xrt::uuid& uuid,xrt::graph& gr,CachedDataset& data,bool use_maps,unsigned count,const fs::path& save):
      graph(gr),cache(data),mapped(use_maps),merged(data.chunks.front().expected.size()),output_dir(save){
        for(unsigned lane=0;lane<2;++lane)kernels[lane]=std::make_unique<Kernels>(device,uuid,lane);
        for(unsigned b=0;b<count;++b){auto bank=std::make_unique<Bank>();for(unsigned lane=0;lane<2;++lane)bank->lanes[lane]=std::make_unique<Buffers>(device,*kernels[lane],cache.chunks.front().input,mapped);banks.push_back(std::move(bank));}
    }
    void prepare(unsigned index,unsigned bank,boexp::Frame& frame,Clock::time_point epoch){
        const auto& in=cache.chunks[index].input;auto& lanes=banks.at(bank)->lanes;
        for(unsigned lane=0;lane<2;++lane)frame.timed("split",lane,epoch,[&]{auto& b=*lanes[lane];if(mapped)boexp::split_to(in,lane,b.mapped_input,in.words.size()/2);else fill_shard_block(in,lane,b.shape);});
        for(unsigned lane=0;lane<2;++lane){auto& b=*lanes[lane];std::vector<uint64_t> packed;
            frame.timed("parameter_pack",lane,epoch,[&]{packed=pack_parameters(b.shape);});
            if(!mapped)frame.timed("input_write",lane,epoch,[&]{b.input.write(b.shape.words.data(),b.shape.words.size()*8,0);});
            frame.timed("parameter_write",lane,epoch,[&]{b.parameters.write(packed.data(),packed.size()*8,0);});
            frame.timed("input_sync",lane,epoch,[&]{b.input.sync(XCL_BO_SYNC_BO_TO_DEVICE);});
            frame.timed("parameter_sync",lane,epoch,[&]{b.parameters.sync(XCL_BO_SYNC_BO_TO_DEVICE);});
            frame.timed("output_poison",lane,epoch,[&]{if(mapped)std::fill_n(b.mapped_output,b.shape.output_words(),UINT64_MAX);else std::fill(b.host_output.begin(),b.host_output.end(),UINT64_MAX);});
            if(!mapped)frame.timed("output_poison_write",lane,epoch,[&]{b.output.write(b.host_output.data(),b.host_output.size()*8,0);});
            frame.timed("output_poison_sync",lane,epoch,[&]{b.output.sync(XCL_BO_SYNC_BO_TO_DEVICE);});
        }
    }
    void start(unsigned index,unsigned bank){
        deadline=Clock::now()+std::chrono::seconds(120);auto& lanes=banks.at(bank)->lanes;
        for(auto& b:lanes)b->reducer.start();auto frames=cache.chunks[index].input.frames()/2;require(frames&&frames<=INT32_MAX,"frame count");graph.run(int(frames));for(auto& b:lanes)b->reader.start();
    }
    void wait(unsigned,unsigned bank){auto& lanes=banks.at(bank)->lanes;for(auto& b:lanes)wait_for_run("reader",b->reader,deadline);for(auto& b:lanes)wait_for_run("reducer",b->reducer,deadline);graph.wait(remaining_time(deadline));}
    void finish(unsigned index,unsigned bank,boexp::Frame& frame,Clock::time_point epoch){
        const auto& chunk=cache.chunks[index];auto& lanes=banks.at(bank)->lanes;
        frame.timed("status",-1,epoch,[&]{for(auto& kernel:kernels){require(kernel->reader.read_register(0x10)==0,"reader status");require(kernel->reducer.read_register(0x10)==0,"reducer status");}});
        frame.timed("merge_poison",-1,epoch,[&]{std::fill(merged.begin(),merged.end(),UINT64_MAX);});
        for(unsigned lane=0;lane<2;++lane){auto& b=*lanes[lane];frame.timed("output_sync",lane,epoch,[&]{b.output.sync(XCL_BO_SYNC_BO_FROM_DEVICE);});
            if(!mapped)frame.timed("output_read",lane,epoch,[&]{b.output.read(b.host_output.data(),b.host_output.size()*8,0);});
            frame.timed("merge",lane,epoch,[&]{boexp::merge_from(chunk.input,lane,mapped?b.mapped_output:b.host_output.data(),b.shape.output_words(),merged);});
        }
        frame.timed("verify",-1,epoch,[&]{compare(merged,chunk.expected,index);});
    }
    void save(unsigned index,unsigned){write_output(output_dir/(cache.chunks[index].spec.id+"_output.bin"),cache.chunks[index].input,merged);}
    void cancel() noexcept {for(auto& bank:banks)for(auto& b:bank->lanes){try{b->reader.abort();}catch(...){}try{b->reducer.abort();}catch(...){}}try{graph.reset();}catch(...){}}
};
double overlap(const boexp::Replay& r,const char* stage){double total=0;for(const auto& f:r.frames)for(unsigned i=0;i<f.count;++i){const auto& a=f.spans[i];if(std::string(a.name)!=stage)continue;for(const auto& g:r.frames)if(g.chunk!=f.chunk)for(unsigned j=0;j<g.count;++j){const auto& b=g.spans[j];if(std::string(b.name)=="execute")total+=std::max(0.,std::min(a.end,b.end)-std::max(a.begin,b.begin));}}return total;}
void run_host(const fs::path& xclbin,const fs::path& root,const fs::path& dir,unsigned reps,unsigned warm,const std::string& mode){
    require(mode=="copy_serial"||mode=="map_serial"||mode=="map_pingpong","invalid mode");require(reps&&reps<=100&&warm<=10,"counts");require(!fs::exists(dir),"result directory exists");
    auto entry=Clock::now();CachedDataset cache(root);auto admitted=Clock::now();validate_boot_xclbin(xclbin);validate_boot_marker();fs::create_directories(dir/"outputs");
    xrt::ini::set("Runtime.enable_flat","false");xrt::ini::set("Runtime.force_program_xclbin","false");xrt::ini::set("Runtime.ert_polling","true");xrt::ini::set("Runtime.xgq_polling","true");
    auto device=xrt::device(0);auto uuid=device.load_xclbin(xclbin.string());auto graph=xrt::graph(device,uuid,"ckks_graph");graph.reset();auto init=Clock::now();
    bool pipeline=mode=="map_pingpong";XrtBackend backend(device,uuid,graph,cache,mode!="copy_serial",pipeline?2:1,dir/"outputs");
    std::unique_ptr<boexp::Worker> worker;if(pipeline)worker=std::make_unique<boexp::Worker>();auto ready=Clock::now();
    std::ofstream setup(dir/"setup.json");setup<<std::setprecision(12)<<"{\"mode\":\""<<mode<<"\",\"dataset_load_ms\":"<<ms(entry,admitted)<<",\"xrt_init_ms\":"<<ms(admitted,init)<<",\"buffer_worker_setup_ms\":"<<ms(init,ready)<<",\"setup_ms\":"<<ms(entry,ready)<<",\"banks\":"<<(pipeline?2:1)<<",\"input_bytes\":"<<cache.input_bytes<<",\"golden_bytes\":"<<cache.golden_bytes<<",\"firmware_changed\":false}\n";setup.close();require(bool(setup),"setup write");
    std::ofstream csv(dir/"iterations.csv"),timeline(dir/"timeline.csv");csv<<std::fixed<<std::setprecision(6);timeline<<std::fixed<<std::setprecision(6);
    csv<<"repetition,warmup,export_only,chunks,replay_wall_ms,execute_sum_ms,stage_work_sum_ms,split_sum_ms,input_write_sum_ms,input_sync_sum_ms,parameter_pack_sum_ms,parameter_write_sum_ms,parameter_sync_sum_ms,output_poison_sum_ms,output_poison_write_sum_ms,output_poison_sync_sum_ms,status_sum_ms,merge_poison_sum_ms,output_sync_sum_ms,output_read_sum_ms,merge_sum_ms,verify_sum_ms,output_save_sum_ms,split_during_other_execute_ms,input_sync_during_other_execute_ms,verified_words\n";
    timeline<<"repetition,warmup,export_only,chunk,bank,stage,lane,begin_ms,end_ms\n";
    const std::array<const char*,17> stages{"split","input_write","input_sync","parameter_pack","parameter_write","parameter_sync","output_poison","output_poison_write","output_poison_sync","status","merge_poison","output_sync","output_read","merge","verify","output_save","execute"};
    std::vector<double> walls,execs;
    try{for(unsigned rep=0;rep<reps+warm+1;++rep){bool exporting=rep==reps+warm,iswarm=rep<warm;
        auto result=boexp::run(backend,cache.chunks.size(),worker.get(),exporting);std::array<double,17> sums{};
        for(const auto& frame:result.frames)for(unsigned i=0;i<frame.count;++i){const auto& s=frame.spans[i];timeline<<rep<<','<<iswarm<<','<<exporting<<','<<frame.chunk<<','<<frame.bank<<','<<s.name<<','<<s.lane<<','<<s.begin<<','<<s.end<<'\n';for(unsigned j=0;j<stages.size();++j)if(std::string(s.name)==stages[j])sums[j]+=s.end-s.begin;}
        double work=0;for(auto s:sums)work+=s;csv<<rep<<','<<iswarm<<','<<exporting<<','<<result.frames.size()<<','<<result.wall_ms<<','<<sums[16]<<','<<work;for(unsigned i=0;i<16;++i)csv<<','<<sums[i];csv<<','<<overlap(result,"split")<<','<<overlap(result,"input_sync")<<','<<cache.golden_bytes/8<<'\n';csv.flush();timeline.flush();require(bool(csv)&&bool(timeline),"trace write");
        if(!iswarm&&!exporting){walls.push_back(result.wall_ms);execs.push_back(sums[16]);}
        std::cout<<"PASS BO_REPLAY mode="<<mode<<" repetition="<<rep<<" warmup="<<iswarm<<" export_only="<<exporting<<" replay_wall_ms="<<result.wall_ms<<" verified_words="<<cache.golden_bytes/8<<'\n'<<std::flush;
    }}catch(...){backend.cancel();if(worker)worker->close();throw;}
    if(worker)worker->close();
    std::ofstream summary(dir/"summary.json");summary<<std::setprecision(12)<<"{\"status\":\"PASS_VERIFIED_BO_REPLAY\",\"mode\":\""<<mode<<"\",\"chunks\":"<<cache.chunks.size()<<",\"measured\":"<<reps<<",\"warmups\":"<<warm<<",\"export_replays\":1,\"replay_wall_median_ms\":"<<median(walls)<<",\"host_observed_execute_sum_median_ms\":"<<median(execs)<<",\"primary_scope\":\"actual wall time: first preparation through last full verification; excludes one-time setup and separate export replay\",\"overlap_scope\":\"host-observed preparation versus XRT run/wait intervals, not hardware DMA event proof\",\"stage_sum_is_not_wall_time\":true,\"firmware_changed\":false}\n";summary.close();require(bool(summary),"summary write");
}
#endif
}
int main(int argc,char** argv){try{
    if(argc==3&&std::string(argv[1])=="--check-data"){check_data(argv[2]);return 0;}
#ifndef CKKSMAC_PARSER_ONLY
    require(argc==7,"usage: bo_host XCLBIN FIXTURE NEW_RESULTS REPS WARMUPS copy_serial|map_serial|map_pingpong");run_host(argv[1],argv[2],argv[3],number(argv[4],100),number(argv[5],10),argv[6]);return 0;
#else
    throw std::runtime_error("parser-only executable");
#endif
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
