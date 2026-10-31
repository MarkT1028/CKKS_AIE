// Independent arithmetic/device model, no XRT, no board performance inference.
#define CKKSMAC_PARSER_ONLY
#define PERF_HOST_NO_MAIN
#include "../reference/host/perf_host.cpp"
#include "../reference/common/dataset_cache.hpp"
#include "../common/finish_overlap.hpp"
#include <fstream>

class AsyncModel {
    struct Lane {std::vector<uint64_t> input,output;};
    struct Bank {std::array<Lane,2> lanes;std::atomic<int> owner{-1};std::atomic<bool> ready{false},busy{false},complete{false};};
    CachedDataset& cache;std::array<Bank,2> banks;std::vector<uint64_t> merged;
    std::thread device;std::exception_ptr device_error;std::atomic<bool> running{false},cancelled{false};
    std::atomic<unsigned> preparing{0};int status_pending=-1;std::string fault;int fault_chunk;fs::path output;
    unsigned starts=0,finishes=0,saved=0,overlapped=0;
    static constexpr uint64_t guard=0xc8632784adfe195bULL;
    void fail(const char* where,unsigned i){if(fault==where&&int(i)==fault_chunk)throw std::runtime_error(std::string("injected ")+where);}
    void guards(){for(auto& b:banks)for(auto& m:b.lanes)for(unsigned j=0;j<8;++j)require(m.input[j]==guard&&m.input[m.input.size()-1-j]==guard&&m.output[j]==guard&&m.output[m.output.size()-1-j]==guard,"guard corruption");}
    void calculate(unsigned i,unsigned b){
        const auto& in=cache.chunks[i].input;auto n=in.n/2;
        std::this_thread::sleep_for(std::chrono::microseconds(250));
        for(auto& m:banks[b].lanes)for(unsigned t=0;t<in.l;++t)for(unsigned j=0;j<n;++j){
            uint64_t q=in.parameters[t].q;U128 s[3]={0,0,0};
            for(unsigned k=0;k<in.k;++k){const auto* p=m.input.data()+8+((size_t(k)*in.l+t)*n+j)*4;
                s[0]=(s[0]+U128(p[0])*p[2]%q)%q;
                s[1]=(s[1]+U128(p[0])*p[3]%q+U128(p[1])*p[2]%q)%q;
                s[2]=(s[2]+U128(p[1])*p[3]%q)%q;
            }
            for(unsigned c=0;c<3;++c)m.output[8+(size_t(t)*n+j)*3+c]=uint64_t(s[c]);
        }
        if(fault=="output"&&int(i)==fault_chunk)banks[b].lanes[1].output[banks[b].lanes[1].output.size()-9]^=1;
    }
public:
    AsyncModel(CachedDataset& c,const fs::path& out={},std::string inject="",int at=-1):cache(c),merged(c.chunks[0].expected.size()),fault(std::move(inject)),fault_chunk(at),output(out){
        for(auto& b:banks)for(auto& m:b.lanes){m.input.assign(c.chunks[0].input.words.size()/2+16,guard);m.output.assign(c.chunks[0].expected.size()/2+16,guard);}
        if(!out.empty())fs::create_directories(out);
    }
    void set_fault(const std::string& name,int at){fault=name;fault_chunk=at;}
    ~AsyncModel(){if(device.joinable())device.join();if(preparing.load())std::terminate();}
    void prepare(unsigned i,unsigned b,boexp::Frame& f,Clock::time_point epoch){
        require(!cancelled&&!banks[b].busy,"prepare reused busy bank");require(preparing.fetch_add(1)==0,"two preparation jobs active");
        struct Cleanup {std::atomic<unsigned>& n;~Cleanup(){--n;}} cleanup{preparing};fail("prepare",i);
        const auto& in=cache.chunks[i].input;
        for(unsigned lane=0;lane<2;++lane)f.timed("split",lane,epoch,[&]{boexp::split_to(in,lane,banks[b].lanes[lane].input.data()+8,in.words.size()/2);});
        for(unsigned lane=0;lane<2;++lane){for(const char* stage:{"parameter_pack","parameter_write","input_sync","parameter_sync","output_poison","output_poison_sync"})
            f.timed(stage,lane,epoch,[&]{if(std::string(stage)=="output_poison")std::fill(banks[b].lanes[lane].output.begin()+8,banks[b].lanes[lane].output.end()-8,UINT64_MAX);});}
        banks[b].owner=i;banks[b].ready=true;banks[b].complete=false;
    }
    void start(unsigned i,unsigned b){
        fail("start",i);require(status_pending==-1,"previous status read after next launch");
        require(!running.exchange(true)&&!banks[b].busy.exchange(true)&&banks[b].ready&&banks[b].owner==int(i),"concurrent graph or wrong bank");
        require(!device.joinable(),"previous device was not joined");device_error=nullptr;++starts;
        device=std::thread([&,i,b]{try{calculate(i,b);}catch(...){device_error=std::current_exception();}});
        fail("launched",i);
    }
    void wait(unsigned i,unsigned b){
        require(running&&banks[b].busy,"wait without device");fail("wait",i);device.join();running=false;
        if(device_error)std::rethrow_exception(device_error);status_pending=i;banks[b].complete=true;
    }
    void complete(unsigned i,unsigned b,boexp::Frame& f,Clock::time_point epoch){
        require(!running&&status_pending==int(i)&&banks[b].complete,"invalid completion order");
        f.timed("status",-1,epoch,[&]{fail("status",i);});status_pending=-1;
    }
    void finish(unsigned i,unsigned b,boexp::Frame& f,Clock::time_point epoch){
        if(status_pending==int(i))complete(i,b,f,epoch); // frozen scheduler checks status at finish entry
        require(banks[b].complete&&banks[b].busy&&banks[b].owner==int(i)&&status_pending==-1,"readback ownership");
        if(running)++overlapped;fail("finish",i);
        const auto& chunk=cache.chunks[i];
        f.timed("merge_poison",-1,epoch,[&]{std::fill(merged.begin(),merged.end(),UINT64_MAX);});
        for(unsigned lane=0;lane<2;++lane){f.timed("output_sync",lane,epoch,[]{});
            f.timed("merge",lane,epoch,[&]{boexp::merge_from(chunk.input,lane,banks[b].lanes[lane].output.data()+8,chunk.expected.size()/2,merged);});}
        f.timed("verify",-1,epoch,[&]{compare(merged,chunk.expected,i);});
        banks[b].ready=false;banks[b].busy=false;++finishes;guards();
    }
    void save(unsigned i,unsigned){
        fail("save",i);require(!output.empty(),"save directory");std::ofstream f(output/(cache.chunks[i].spec.id+".raw"),std::ios::binary);
        f.write(reinterpret_cast<const char*>(merged.data()),merged.size()*8);f.close();require(bool(f),"model save");++saved;
    }
    void cancel() noexcept {cancelled=true;if(device.joinable())device.join();running=false;}
    void checked(unsigned count,unsigned exported,bool overlap){require(starts==count&&finishes==count&&saved==exported&&!running&&preparing==0,"unfinished model work");if(overlap&&cache.chunks.size()>1)require(overlapped>0,"no finish during next device execution");guards();}
};
template<class Fn>void rejected(Fn fn){bool caught=false;try{fn();}catch(const std::exception&){caught=true;}require(caught,"injected fault was accepted");}
void trace_check(const boexp::Replay& r,bool overlap,bool save){
    for(unsigned i=0;i<r.frames.size();++i){const auto& f=r.frames[i];require(f.chunk==i&&f.bank==i%2&&f.count==(save?23U:22U),"model trace identity/count");
        for(unsigned j=0;j<f.count;++j){auto s=f.spans[j];require(s.end>=s.begin&&s.end<=r.wall_ms+.001,"trace bounds");if(j)require(f.spans[j-1].end<=s.begin+.001,"own frame stages overlap");}
        auto find=[&](unsigned n,const std::string& stage){for(unsigned j=0;j<r.frames[n].count;++j)if(stage==r.frames[n].spans[j].name)return r.frames[n].spans[j];throw std::runtime_error("missing span");};
        if(i){auto prev=find(i-1,"execute"),exec=find(i,"execute"),status=find(i-1,"status");require(exec.begin>=prev.end&&exec.begin>=status.end,"graphs overlap/status race");if(overlap)require(exec.begin<=find(i-1,"merge_poison").begin,"next graph did not precede prior readback");}
        if(i>=2)require(f.spans[0].begin>=find(i-2,save?"output_save":"verify").end,"bank overwritten before verification/export");
    }
}

#include "../common/compact_dataset.hpp"
int main(int argc,char**argv){try{
 require(argc==2,"test COMPACT_FIXTURE");CachedDataset cache;load_compact_group(cache,argv[1],5);const auto n=cache.chunks.size();
 {AsyncModel model(cache);boexp::Worker worker;unsigned runs=0;
 for(unsigned rep=0;rep<3;++rep)for(unsigned ord=0;ord<6;++ord){auto g=rep%2?ord:5-ord;load_compact_group(cache,argv[1],g);auto result=boexp::run_finish_overlap(model,cache.chunks.size(),worker,false);trace_check(result,true,false);++runs;}
 worker.close();model.checked(n*runs,0,true);}
 for(const std::string fault:{"prepare","start","launched","wait","status","finish","output"}){
  CachedDataset c;load_compact_group(c,argv[1],5);AsyncModel model(c);boexp::Worker worker;
  for(unsigned g:{5U,4U}){load_compact_group(c,argv[1],g);boexp::run_finish_overlap(model,c.chunks.size(),worker,false);}
  model.set_fault(fault,0);load_compact_group(c,argv[1],3);rejected([&]{boexp::run_finish_overlap(model,c.chunks.size(),worker,false);});worker.close();
 }
 std::cout<<"PASS_FULL_SIX_GROUP_PERSISTENT_BACKEND_WORKER_AND_GROUP_TRANSITION_FAULTS variants=7 repetitions=3 groups=6 shared_resources=1 board_performance=NOT_MEASURED\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
