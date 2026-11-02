// FUNCTIONAL TEST ONLY. This translation unit has no XRT execution path.
#define CKKSMAC_PARSER_ONLY
#define PERF_HOST_NO_MAIN
#include "../reference/host/perf_host.cpp"
#include "../reference/common/dataset_cache.hpp"
#include "../common/replay.hpp"

struct FakeLane {InputCase copied;std::vector<uint64_t> input,output,host_output;};
struct FakeBank {std::array<FakeLane,2> lanes;std::atomic<bool> busy{false};std::atomic<int> prepared{-1};};
void save_test_output(const fs::path& path,const InputCase& in,const std::vector<uint64_t>& out){
    std::ofstream f(path,std::ios::binary);require(bool(f),"test output open");f.write("CKKSMAC1",8);
    auto put=[&](uint64_t x,unsigned n){for(unsigned j=0;j<n;++j)f.put(char((x>>(j*8))&255));};
    for(auto x:std::array<uint32_t,10>{1,2,in.n,in.l,in.k,3,1,64,0,0})put(x,4);
    put(out.size(),8);put(0,8);for(const auto& p:in.parameters){put(p.q,8);put(p.mu_lo,8);put(p.mu_hi,8);}for(auto x:out)put(x,8);
    f.close();require(bool(f),"test output close");
}
class FakeBackend {
    CachedDataset& cache;bool mapped;std::array<FakeBank,2> banks;std::vector<uint64_t> merged;
    std::atomic<bool> cancelled{false};std::atomic<unsigned> preparing{0};
    fs::path output;std::string fault;unsigned starts=0,finishes=0;
    static constexpr uint64_t canary=0x1982476adef13579ULL;
    void guards(FakeLane& lane){for(unsigned i=0;i<8;++i){require(lane.input[i]==canary&&lane.input[lane.input.size()-1-i]==canary,"input guard changed");require(lane.output[i]==canary&&lane.output[lane.output.size()-1-i]==canary,"output guard changed");}}
public:
    FakeBackend(CachedDataset& c,bool mapping,const fs::path& dest,const std::string& inject=""):
      cache(c),mapped(mapping),merged(c.chunks[0].expected.size()),output(dest),fault(inject){
        for(auto& bank:banks)for(auto& lane:bank.lanes){lane.input.assign(c.chunks[0].input.words.size()/2+16,canary);lane.output.assign(c.chunks[0].expected.size()/2+16,canary);lane.host_output.resize(c.chunks[0].expected.size()/2);}
        if(!output.empty())fs::create_directories(output);
    }
    ~FakeBackend(){if(preparing.load()!=0)std::terminate();}
    void prepare(unsigned index,unsigned b,boexp::Frame& frame,Clock::time_point epoch){
        require(!cancelled&&!banks[b].busy,"preparing a busy/cancelled bank");++preparing;
        struct Cleanup {std::atomic<unsigned>& n;~Cleanup(){--n;}} cleanup{preparing};
        if(fault=="prepare"&&index==1)throw std::runtime_error("injected preparation failure");
        const auto& in=cache.chunks[index].input;auto& bank=banks[b];
        for(unsigned lane=0;lane<2;++lane){auto& mem=bank.lanes[lane];guards(mem);
            frame.timed("split",lane,epoch,[&]{if(mapped)boexp::split_to(in,lane,mem.input.data()+8,mem.input.size()-16);else fill_shard_block(in,lane,mem.copied);});
            if(!mapped)frame.timed("input_write",lane,epoch,[&]{std::copy(mem.copied.words.begin(),mem.copied.words.end(),mem.input.begin()+8);});
            frame.timed("input_sync",lane,epoch,[]{});
            frame.timed("output_poison",lane,epoch,[&]{std::fill(mem.output.begin()+8,mem.output.end()-8,UINT64_MAX);});
        }
        bank.prepared=index;
    }
    void start(unsigned index,unsigned b){require(!cancelled&&banks[b].prepared==int(index)&&!banks[b].busy.exchange(true),"start ownership/order violation");++starts;}
    void wait(unsigned index,unsigned b){
        require(banks[b].busy,"wait without run");if(fault=="wait"&&index==0)throw std::runtime_error("injected device wait failure");
        std::this_thread::sleep_for(std::chrono::milliseconds(2));const auto& in=cache.chunks[index].input;auto n=in.n/2;
        for(auto& lane:banks[b].lanes)for(unsigned t=0;t<in.l;++t)for(unsigned j=0;j<n;++j){
            const uint64_t q=in.parameters[t].q;U128 sums[3]={0,0,0};
            // Independently reduce every product, unlike the CPU production core.
            for(unsigned pair=0;pair<in.k;++pair){const auto* p=lane.input.data()+8+((size_t(pair)*in.l+t)*n+j)*4;
                sums[0]=(sums[0]+U128(p[0])*p[2]%q)%q;
                sums[1]=(sums[1]+U128(p[0])*p[3]%q+U128(p[1])*p[2]%q)%q;
                sums[2]=(sums[2]+U128(p[1])*p[3]%q)%q;
            }
            for(unsigned c=0;c<3;++c)lane.output[8+(size_t(t)*n+j)*3+c]=uint64_t(sums[c]);
        }
        if(fault=="output"&&index==0)banks[b].lanes[0].output[8]^=1;
    }
    void finish(unsigned index,unsigned b,boexp::Frame& frame,Clock::time_point epoch){
        require(banks[b].busy,"readback without run");const auto& chunk=cache.chunks[index];std::fill(merged.begin(),merged.end(),UINT64_MAX);
        for(unsigned lane=0;lane<2;++lane){auto& mem=banks[b].lanes[lane];guards(mem);
            frame.timed("output_sync",lane,epoch,[]{});
            if(!mapped)frame.timed("output_read",lane,epoch,[&]{std::copy(mem.output.begin()+8,mem.output.end()-8,mem.host_output.begin());});
            frame.timed("merge",lane,epoch,[&]{boexp::merge_from(chunk.input,lane,mapped?mem.output.data()+8:mem.host_output.data(),chunk.expected.size()/2,merged);});
        }
        frame.timed("verify",-1,epoch,[&]{compare(merged,chunk.expected,index);});banks[b].busy=false;++finishes;
    }
    void save(unsigned index,unsigned){save_test_output(output/(cache.chunks[index].spec.id+"_output.bin"),cache.chunks[index].input,merged);}
    void cancel() noexcept {cancelled=true;for(auto& bank:banks)bank.busy=false;}
    void checked(unsigned expected){require(starts==expected&&finishes==expected&&preparing==0,"unfinished frame/thread");}
};
template<class Fn> void reject(Fn fn){bool caught=false;try{fn();}catch(const std::exception&){caught=true;}require(caught,"fault accepted");}
int main(int argc,char** argv){try{
    require(argc==3,"test FIXTURE NEW_RESULT_ROOT");fs::path dest=argv[2];require(!fs::exists(dest),"test results exist");fs::create_directories(dest);CachedDataset cache(argv[1]);
    unsigned modes=0;
    for(const auto& mode:{std::string("copy_serial"),std::string("map_serial"),std::string("map_pingpong")}){
        FakeBackend backend(cache,mode!="copy_serial",dest/mode);std::unique_ptr<boexp::Worker> worker;
        if(mode=="map_pingpong")worker=std::make_unique<boexp::Worker>();
        for(unsigned rep=0;rep<3;++rep){auto result=boexp::run(backend,cache.chunks.size(),worker.get(),rep==2);require(result.frames.size()==cache.chunks.size(),"frame count");for(unsigned i=0;i<result.frames.size();++i)require(result.frames[i].chunk==i&&result.frames[i].bank==(worker?i%2:0),"trace bank order");}
        if(worker)worker->close();backend.checked(cache.chunks.size()*3);++modes;
    }
    auto& first=cache.chunks.front().input;std::vector<uint64_t> out(first.words.size()/2);
    reject([&]{boexp::split_to(first,2,out.data(),out.size());});reject([&]{boexp::split_to(first,0,out.data(),out.size()-1);});reject([&]{boexp::split_to(first,0,first.words.data(),out.size());});reject([&]{boexp::split_to(first,0,nullptr,out.size());});
    for(const std::string fault:{"prepare","wait","output"}){
        if(fault=="prepare"&&cache.chunks.size()<2)continue;
        FakeBackend backend(cache,true,{},fault);boexp::Worker worker;
        reject([&]{boexp::run(backend,cache.chunks.size(),&worker,false);});worker.close();reject([&]{worker.submit([]{});});
    }
    {boexp::Worker worker;reject([&]{worker.wait();});worker.submit([]{throw std::runtime_error("worker fault");});reject([&]{worker.wait();});std::atomic<bool> complete{false};worker.submit([&]{complete=true;});worker.wait();require(complete,"worker exception recovery");}
    {std::atomic<bool> complete{false};{boexp::Worker worker;worker.submit([&]{std::this_thread::sleep_for(std::chrono::milliseconds(1));complete=true;});}require(complete,"worker close did not join pending job");}
    std::cout<<"PASS FUNCTIONAL_SCHEDULE_ONLY modes="<<modes<<" repetitions_each=3 chunks="<<cache.chunks.size()<<" saved_output_sets=3 canaries=1 failure_cleanup=1 alias_bounds=1 board_performance=NOT_MEASURED\n";return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
