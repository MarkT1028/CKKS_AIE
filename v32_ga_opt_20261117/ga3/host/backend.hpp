#pragma once
namespace { namespace finishopt {
struct Task {unsigned slot,group,window;};
class Backend {
    struct ReadBuffer {
        xrt::bo bo;uint64_t* words;std::string key;
        ReadBuffer(const xrt::device& d,size_t bytes,unsigned group):
            bo(d,bytes,xrt::bo::flags::cacheable,group),words(bo.map<uint64_t*>()){
            require(words,"input BO map failed");
        }
    };
    struct OutputBuffer {
        xrt::bo output,parameters;xrt::run reader,reducer;uint64_t* words;InputCase shape;
        OutputBuffer(const xrt::device& d,Kernels& k,const InputCase& full):
            output(d,full.output_words()*8/2,xrt::bo::flags::cacheable,k.reducer.group_id(1)),
            parameters(d,full.l*32,k.reducer.group_id(2)),reader(k.reader),reducer(k.reducer),
            words(output.map<uint64_t*>()){
            require(words,"output BO map failed");reducer.set_arg(1,output);reducer.set_arg(2,parameters);
        }
    };
    std::array<std::unique_ptr<Kernels>,2> kernels;
    std::array<std::unique_ptr<ReadBuffer>,4> weights;
    std::array<std::unique_ptr<ReadBuffer>,2> babies;
    std::array<std::array<std::unique_ptr<OutputBuffer>,2>,2> outputs;
    std::array<Window*,2> windows{};
    std::array<uint64_t,2> copied{},synced{},hits{};
    std::vector<Task> tasks;std::vector<uint64_t> merged;
    const finishsha::Engine& engine;bool running=false,direct=true;
    Clock::time_point deadline;
    uint64_t digest_count=0,digest_bytes=0;
    fs::path export_root;bool export_all=false;
    void upload(ReadBuffer& bo,const std::string& key,const std::vector<uint64_t>& data,
                const char* copy_stage,const char* sync_stage,unsigned slot,boexp::Frame& f,Clock::time_point epoch){
        require(!key.empty()&&!data.empty(),"input key/data empty");
        if(bo.key==key){++hits[slot];return;}
        size_t bytes=data.size()*8;
        f.timed(copy_stage,-1,epoch,[&]{std::memcpy(bo.words,data.data(),bytes);});copied[slot]+=bytes;
        f.timed(sync_stage,-1,epoch,[&]{bo.bo.sync(XCL_BO_SYNC_BO_TO_DEVICE,bytes,0);});synced[slot]+=bytes;
        bo.key=key;
    }
public:
    static constexpr uint64_t maximum_page_rounded_BO_bytes=207634432;
    Backend(const xrt::device& d,const xrt::uuid& id,const InputCase& maximum,const finishsha::Engine& hash):engine(hash){
        for(unsigned l=0;l<2;++l)kernels[l]=std::make_unique<Kernels>(d,id,l);
        const auto wa=kernels[0]->reader.group_id(0),ba=kernels[0]->reader.group_id(1);
        require(wa==kernels[1]->reader.group_id(0)&&ba==kernels[1]->reader.group_id(1),"input memory groups differ");
        const size_t bytes=size_t(maximum.n)*maximum.l*maximum.k*2*8;
        for(auto& b:weights)b=std::make_unique<ReadBuffer>(d,bytes,wa);
        for(auto& b:babies)b=std::make_unique<ReadBuffer>(d,bytes,ba);
        for(auto& bank:outputs)for(unsigned l=0;l<2;++l)bank[l]=std::make_unique<OutputBuffer>(d,*kernels[l],maximum);
    }
    void configure(const std::vector<Window*>& contexts,bool ascending,bool direct_hash,const fs::path& destination,bool save_all){
        require(!running&&!contexts.empty()&&contexts.size()<=2,"batch configuration ownership");
        tasks.clear();windows.fill(nullptr);copied.fill(0);synced.fill(0);hits.fill(0);
        direct=direct_hash;export_root=destination;export_all=save_all;
        const auto& first=*contexts[0];
        for(unsigned s=0;s<contexts.size();++s){
            auto& w=*contexts[s];require(w.active&&same_parameters(first.shape,w.shape)&&w.tower==first.tower&&w.coefficient==first.coefficient,"batch crosses immutable weight block");
            for(unsigned g=0;g<4;++g)require(w.weight_keys[g]==first.weight_keys[g],"batch weights differ");
            windows[s]=&w;
            for(unsigned j=0;j<4;++j)tasks.push_back({s,ascending?j:3-j,w.ct});
        }
        for(auto& bank:outputs)for(unsigned l=0;l<2;++l){
            auto& b=*bank[l];b.shape=first.shape;b.shape.n/=2;
            b.reader.set_arg(3,b.shape.n);b.reader.set_arg(4,b.shape.l);b.reader.set_arg(5,b.shape.k);b.reader.set_arg(6,l);
            b.reducer.set_arg(3,b.shape.n);b.reducer.set_arg(4,b.shape.l);b.reducer.set_arg(5,b.shape.k);
        }
        if(!direct)merged.resize(first.shape.output_words());
    }
    const std::vector<Task>& schedule()const{return tasks;}
    void prepare(unsigned i,unsigned bank,boexp::Frame& f,Clock::time_point epoch){
        const auto job=tasks.at(i);auto& w=*windows.at(job.slot);
        require(w.active&&w.baby.size()==size_t(w.shape.n)*w.shape.l*w.shape.k*2,"input window ownership/shape");
        upload(*babies[job.slot],w.baby_key,w.baby,"baby_copy","baby_sync",job.slot,f,epoch);
        upload(*weights[job.group],w.weight_keys[job.group],*w.weights[job.group],"weight_copy","weight_sync",job.slot,f,epoch);
        for(unsigned l=0;l<2;++l){
            auto& b=*outputs.at(bank)[l];b.reader.set_arg(0,weights[job.group]->bo);b.reader.set_arg(1,babies[job.slot]->bo);
            std::vector<uint64_t> parameters;
            f.timed("parameter_pack",l,epoch,[&]{parameters=pack_parameters(b.shape);});
            f.timed("parameter_write",l,epoch,[&]{b.parameters.write(parameters.data(),parameters.size()*8,0);});
            f.timed("parameter_sync",l,epoch,[&]{b.parameters.sync(XCL_BO_SYNC_BO_TO_DEVICE,b.shape.l*32,0);});
            f.timed("output_poison",l,epoch,[&]{std::fill_n(b.words,b.shape.output_words(),UINT64_MAX);});
            f.timed("output_poison_sync",l,epoch,[&]{b.output.sync(XCL_BO_SYNC_BO_TO_DEVICE,b.shape.output_words()*8,0);});
        }
    }
    void start(unsigned,unsigned bank){
        require(!running,"more than one active CU invocation");running=true;deadline=Clock::now()+std::chrono::seconds(120);
        for(auto& b:outputs[bank])b->reducer.start();
        for(auto& b:outputs[bank])b->reader.start();
    }
    void wait(unsigned,unsigned bank){
        for(auto& b:outputs[bank])wait_for_run("reader",b->reader,deadline);
        for(auto& b:outputs[bank])wait_for_run("reducer",b->reducer,deadline);
    }
    void complete(unsigned,unsigned,boexp::Frame& f,Clock::time_point epoch){
        f.timed("status",-1,epoch,[&]{for(auto& k:kernels){require(k->reader.read_register(0x10)==0,"reader status failed");require(k->reducer.read_register(0x10)==0,"reducer status failed");}running=false;});
    }
    void finish(unsigned i,unsigned bank,boexp::Frame& f,Clock::time_point epoch){
        const auto job=tasks.at(i);auto& w=*windows.at(job.slot);auto& out=outputs[bank];
        for(unsigned l=0;l<2;++l){auto& b=*out[l];f.timed("output_sync",l,epoch,[&]{b.output.sync(XCL_BO_SYNC_BO_FROM_DEVICE,b.shape.output_words()*8,0);});}
        std::string digest;
        if(direct){
            f.timed("canonical_sha256",-1,epoch,[&]{digest=finishsha::split_output_digest(engine,w.shape,out[0]->words,out[1]->words,out[0]->shape.output_words());});
        }else{
            for(unsigned l=0;l<2;++l)f.timed("merge_copy",l,epoch,[&]{
                const size_t n=size_t(w.shape.n/2)*3;
                for(unsigned t=0;t<w.shape.l;++t)std::memcpy(merged.data()+size_t(t)*n*2+l*n,out[l]->words+t*n,n*8);
            });
            f.timed("canonical_sha256",-1,epoch,[&]{digest=finishsha::output_digest(engine,w.shape,merged);});
        }
        f.timed("verify_digest",-1,epoch,[&]{w.verify(job.group,digest);});
        ++digest_count;digest_bytes+=finishsha::canonical_header(w.shape,w.shape.output_words()).size()+w.shape.output_words()*8;
    }
    void save(unsigned i,unsigned bank){
        const auto job=tasks.at(i);const auto& w=*windows.at(job.slot);
        require(w.active&&(w.mask&(1U<<job.group)),"export before verified output");
        auto parent=export_root/("r"+std::to_string(w.tower)+"_c"+std::to_string(w.coefficient)+"_o"+std::to_string(w.ct))/("group_"+std::to_string(job.group));
        fs::create_directories(parent);const auto path=parent/"chunk_0_output.bin";
        streamio::save_verified_digest(path,w.digests[job.group]);
        const bool sample=(w.tower==0&&w.coefficient==0&&w.ct==0)||(w.shape.l<16&&w.coefficient==122880&&w.ct==15);
        if(export_all||sample){
            windowio::Fd fd;fd.value=::open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);require(fd.value>=0,"export exists or cannot create");
            const auto header=finishsha::canonical_header(w.shape,w.shape.output_words());streamio::output_write(fd.value,header.data(),header.size());
            const size_t n=size_t(w.shape.n/2)*3;
            for(unsigned t=0;t<w.shape.l;++t)for(unsigned l=0;l<2;++l)streamio::output_write(fd.value,outputs[bank][l]->words+t*n,n*8);
            int status=::close(fd.value);fd.value=-1;require(status==0,"export close failed");
        }
    }
    uint64_t copied_bytes(unsigned slot)const{return copied.at(slot);}
    uint64_t synced_bytes(unsigned slot)const{return synced.at(slot);}
    uint64_t cache_hits(unsigned slot)const{return hits.at(slot);}
    uint64_t hashed_outputs()const{return digest_count;}
    uint64_t hashed_bytes()const{return digest_bytes;}
    void cancel()noexcept{
        for(auto& bank:outputs)for(auto& b:bank)if(b){try{b->reader.abort();}catch(...){}try{b->reducer.abort();}catch(...){}}
        running=false;
    }
};
} }
