#include "wire.hpp"
#include <array>
#include <chrono>
#include <iostream>
#include <optional>
#include <cstring>
#include <unistd.h>
#ifndef GA_MODEL
#ifdef GA_XRT_CONTRACT
#define CKKSMAC_PARSER_ONLY
#else
#include <ext/stdio_filebuf.h>
#endif
#define FULL_HS4_BACKEND_ONLY
#include <variants/v32_native_pl_2_pipe/host/bo_host.cpp>
#ifdef GA_XRT_CONTRACT
#include <tests/mock_xrt.hpp>
#endif
#endif

using ga::Tile;
using U128 = unsigned __int128;
using Tick = std::chrono::steady_clock;

#ifdef GA_MODEL
class Engine {
    std::array<std::vector<uint64_t>,ga::weight_slots> weights;
    std::vector<uint64_t> baby, output;
public:
    void upload(const Tile& t) {
        auto receive=[&](auto& v){v.resize(t.input_words());ga::read_words(std::cin,v.data(),v.size());ga::input_range(t,v.data());};
        if (!(t.flags&ga::reuse_weight)) receive(weights[t.slot]);
        if (!(t.flags&ga::reuse_baby)) receive(baby);
    }
    uint64_t run(const Tile& t) {
        auto start=Tick::now();
        output.resize(t.output_words());
        const auto& a=weights[t.slot];
        for (unsigned l=0;l<t.l;++l) for (unsigned j=0;j<t.n;++j) {
            U128 sum[3]{};
            for (unsigned k=0;k<t.k;++k) {
                const size_t p=((size_t(k)*t.l+l)*t.n+j)*2;
                U128 a0=a[p],a1=a[p+1],b0=baby[p],b1=baby[p+1];
                sum[0]+=a0*b0;sum[1]+=a0*b1+a1*b0;sum[2]+=a1*b1;
            }
            for(unsigned c=0;c<3;++c) output[(size_t(l)*t.n+j)*3+c]=uint64_t(sum[c]%t.q[l]);
        }
        return std::chrono::duration_cast<std::chrono::nanoseconds>(Tick::now()-start).count();
    }
    void emit(std::ostream& out,const Tile&) { ga::write_words(out,output.data(),output.size()); }
};
#else
class Engine {
    struct Lane {
        Kernels kernels;
        xrt::bo output, params;
        xrt::run reader, reducer;
        uint64_t* data;
        Lane(const xrt::device& device,const xrt::uuid& uuid,unsigned lane)
            : kernels(device,uuid,lane),
              output(device,ga::tile_n/2*ga::tile_l*3*8,xrt::bo::flags::cacheable,kernels.reducer.group_id(1)),
              params(device,ga::tile_l*32,xrt::bo::flags::cacheable,kernels.reducer.group_id(2)),
              reader(kernels.reader),reducer(kernels.reducer),data(output.map<uint64_t*>()) {
            ga::check(data!=nullptr,"map output BO");
            reducer.set_arg(1,output);reducer.set_arg(2,params);reader.set_arg(6,lane);
        }
    };
    std::array<std::unique_ptr<Lane>,2> lanes;
    std::vector<xrt::bo> weights;
    std::optional<xrt::bo> baby;
    fs::path active;
public:
    Engine(const xrt::device& d,const xrt::uuid& id,fs::path marker):active(std::move(marker)) {
        for(unsigned i=0;i<2;++i)lanes[i]=std::make_unique<Lane>(d,id,i);
        auto a=lanes[0]->kernels.reader.group_id(0),b=lanes[0]->kernels.reader.group_id(1);
        ga::check(a==lanes[1]->kernels.reader.group_id(0)&&b==lanes[1]->kernels.reader.group_id(1),"lane memory groups differ");
        const size_t bytes=size_t(ga::tile_n)*ga::tile_l*ga::terms*16;
        for(unsigned i=0;i<ga::weight_slots;++i) weights.emplace_back(d,bytes,xrt::bo::flags::cacheable,a);
        baby.emplace(d,bytes,xrt::bo::flags::cacheable,b);
    }
    void upload(const Tile& t) {
        auto receive=[&](xrt::bo& bo){auto p=bo.map<uint64_t*>();ga::check(p!=nullptr,"map input BO");ga::read_words(std::cin,p,t.input_words());ga::input_range(t,p);bo.sync(XCL_BO_SYNC_BO_TO_DEVICE,t.input_words()*8,0);};
        if (!(t.flags&ga::reuse_weight)) receive(weights[t.slot]);
        if (!(t.flags&ga::reuse_baby)) receive(*baby);
    }
    uint64_t run(const Tile& t) {
        auto start=Tick::now();
        InputCase shape;shape.n=t.n/2;shape.l=t.l;shape.k=t.k;
        for(auto q:t.q){U128 mu=~U128(0)/q;shape.parameters.push_back({q,uint64_t(mu),uint64_t(mu>>64)});}
        const auto parameters=pack_parameters(shape);
        const size_t words=t.output_words()/2;
        for(auto& lane:lanes){
            lane->reader.set_arg(0,weights[t.slot]);lane->reader.set_arg(1,*baby);
            lane->reader.set_arg(3,shape.n);lane->reader.set_arg(4,t.l);lane->reader.set_arg(5,t.k);
            lane->reducer.set_arg(3,shape.n);lane->reducer.set_arg(4,t.l);lane->reducer.set_arg(5,t.k);
            lane->params.write(parameters.data(),parameters.size()*8,0);
            lane->params.sync(XCL_BO_SYNC_BO_TO_DEVICE,parameters.size()*8,0);
            std::fill_n(lane->data,words,UINT64_MAX);
            lane->output.sync(XCL_BO_SYNC_BO_TO_DEVICE,words*8,0);
        }
        { std::ofstream f(active,std::ios::out|std::ios::trunc);f<<"PL launch active\n";f.close();ga::check(bool(f),"write recovery marker"); }
        try {
            const auto deadline=Tick::now()+std::chrono::seconds(120);
            for(auto& lane:lanes)lane->reducer.start();
            for(auto& lane:lanes)lane->reader.start();
            for(auto& lane:lanes)wait_for_run("reader",lane->reader,deadline);
            for(auto& lane:lanes)wait_for_run("reducer",lane->reducer,deadline);
            for(auto& lane:lanes){
                ga::check(lane->kernels.reader.read_register(0x10)==0&&lane->kernels.reducer.read_register(0x10)==0,"PL kernel status");
                lane->output.sync(XCL_BO_SYNC_BO_FROM_DEVICE,words*8,0);
                size_t offset=0;
                for(auto q:t.q)for(unsigned j=0;j<shape.n*3;++j)ga::check(lane->data[offset++]<q,"missing or noncanonical output residue");
            }
        } catch (...) {
            for(auto& lane:lanes){try{lane->reader.abort();}catch(...){}try{lane->reducer.abort();}catch(...){}}
            throw;
        }
        ga::check(fs::remove(active),"remove own completed launch marker");
        return std::chrono::duration_cast<std::chrono::nanoseconds>(Tick::now()-start).count();
    }
    void emit(std::ostream& out,const Tile& t) {
        const size_t half=t.n/2*3;
        for(unsigned l=0;l<t.l;++l)for(const auto& lane:lanes)ga::write_words(out,lane->data+l*half,half);
    }
};
#endif

int main(int argc,char** argv) {
    try {
        std::ios::sync_with_stdio(false);std::cin.tie(nullptr);ga::little_endian();
#ifdef GA_MODEL
        ga::check(argc==1,"usage: ga_model");Engine engine;constexpr uint32_t hardware=0;
        auto& out=std::cout;
#elif defined(GA_XRT_CONTRACT)
        ga::check(argc==1,"usage: ga_xrt_contract");
        const auto marker=fs::temp_directory_path()/("v32-ga-xrt-contract-"+std::to_string(getpid()));
        ga::check(!fs::exists(marker),"contract marker already exists");
        Engine engine(xrt::device{},xrt::uuid{},marker);constexpr uint32_t hardware=0;
        auto& out=std::cout;
#else
        ga::check(argc==3,"usage: ga_server XCLBIN ACTIVE_MARKER");
        // Keep C and C++ runtime diagnostics outside the binary reply stream.
        const int reply_fd=dup(STDOUT_FILENO);
        ga::check(reply_fd>=0,"duplicate reply descriptor");
        __gnu_cxx::stdio_filebuf<char> reply_buffer(reply_fd,std::ios::out|std::ios::binary);
        std::ostream out(&reply_buffer);
        ga::check(dup2(STDERR_FILENO,STDOUT_FILENO)>=0,"redirect XRT diagnostics");
        validate_boot_xclbin(argv[1]);validate_boot_marker();
        xrt::ini::set("Runtime.enable_flat","false");xrt::ini::set("Runtime.force_program_xclbin","false");
        xrt::ini::set("Runtime.ert_polling","true");xrt::ini::set("Runtime.xgq_polling","true");
        xrt::device device(0);auto uuid=device.load_xclbin(argv[1]);
        Engine engine(device,uuid,argv[2]);constexpr uint32_t hardware=1;
#endif
        ga::write(out,ga::hello);ga::write(out,hardware);out.flush();
        ga::check(bool(out),"flush server handshake");
        std::array<std::optional<Tile>,ga::weight_slots> weights;
        std::optional<Tile> baby;uint32_t expected=1;
        for(;;){
            const auto op=ga::read<uint32_t>(std::cin);if(op==ga::stop)return 0;
            ga::check(op==ga::request,"unexpected opcode");auto t=ga::receive_tile(std::cin);
            ga::check(t.id==expected++,"out-of-order tile ID");
            if(t.flags&ga::reuse_weight)ga::check(weights[t.slot]&&weights[t.slot]->same_shape(t),"uninitialized or wrong-shape weight reuse");
            if(t.flags&ga::reuse_baby)ga::check(baby&&baby->same_shape(t),"uninitialized or wrong-shape baby reuse");
            auto tick=Tick::now();engine.upload(t);
            uint64_t upload=std::chrono::duration_cast<std::chrono::nanoseconds>(Tick::now()-tick).count();
            if(!(t.flags&ga::reuse_weight))weights[t.slot]=t;
            if(!(t.flags&ga::reuse_baby))baby=t;
            auto elapsed=engine.run(t);
            for(auto v:{ga::reply,t.id,t.n,t.l,t.k})ga::write(out,v);
            ga::write(out,upload);ga::write(out,elapsed);engine.emit(out,t);out.flush();
            ga::check(bool(out),"flush tile reply");
        }
    }catch(const std::exception& e){std::cerr<<"GA_SERVER_FAIL: "<<e.what()<<'\n';return 1;}
}
