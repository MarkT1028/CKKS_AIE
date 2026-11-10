#pragma once
// Software contract model only. Separate host/device images, asynchronous
// readers, and ownership guards. This is never board performance evidence.
#include <future>
#include <thread>
#include <atomic>
#include <map>
namespace xrt {
inline bool corrupt_input_sync=false,corrupt_output=false;
struct device{};struct uuid{};
struct Storage {
    std::vector<uint64_t> host,dev;std::atomic<unsigned> readers{0},writers{0};
    explicit Storage(size_t bytes):host(bytes/8),dev(bytes/8){}
};
class bo {
public:
    enum class flags {cacheable};std::shared_ptr<Storage> storage;
    bo(const device&,size_t bytes,flags,unsigned):storage(std::make_shared<Storage>(bytes)){require(bytes%8==0,"model BO alignment");}
    bo(const device& d,size_t bytes,unsigned group):bo(d,bytes,flags::cacheable,group){}
    template<class T>T map(){return reinterpret_cast<T>(storage->host.data());}
    void write(const void* data,size_t bytes,size_t offset){require(offset+bytes<=storage->host.size()*8,"model write bounds");std::memcpy(reinterpret_cast<uint8_t*>(storage->host.data())+offset,data,bytes);}
    void sync(int direction,size_t bytes,size_t offset){
        require(offset+bytes<=storage->host.size()*8,"model sync bounds");
        require(storage->writers.load()==0&&(direction!=0||storage->readers.load()==0),"model active BO overwritten or read too early");
        auto& to=direction==0?storage->dev:storage->host;const auto& from=direction==0?storage->host:storage->dev;
        std::memcpy(reinterpret_cast<uint8_t*>(to.data())+offset,reinterpret_cast<const uint8_t*>(from.data())+offset,bytes);
        if(corrupt_input_sync&&direction==0&&bytes>100000)to[0]^=1;
    }
};
struct kernel {
    bool reader;unsigned lane;
    unsigned group_id(unsigned arg)const{return reader?arg:arg+4;}
    unsigned read_register(unsigned)const{return 0;}
};
struct run;
inline run* reducers[2]{};
struct run {
    kernel k;std::map<unsigned,bo> buffers;std::map<unsigned,unsigned> args;std::future<void> work;
    explicit run(const kernel& in):k(in){}
    void set_arg(unsigned arg,const bo& value){buffers.insert_or_assign(arg,value);}
    void set_arg(unsigned arg,unsigned value){args[arg]=value;}
    void start(){
        if(!k.reader){reducers[k.lane]=this;return;}
        require(!work.valid(),"model reader relaunch before wait");auto* reducer=reducers[k.lane];require(reducer,"model reducer must start first");
        const unsigned n=args.at(3),l=args.at(4),count=args.at(5),lane=args.at(6);
        require(lane==k.lane&&reducer->args.at(3)==n&&reducer->args.at(4)==l&&reducer->args.at(5)==count,"model runtime shape/args");
        auto a=buffers.at(0).storage,b=buffers.at(1).storage,o=reducer->buffers.at(1).storage,p=reducer->buffers.at(2).storage;
        ++a->readers;++b->readers;++p->readers;++o->writers;
        const bool corrupt=corrupt_output;
        work=std::async(std::launch::async,[=]{
            struct Done {std::shared_ptr<Storage>a,b,o,p;~Done(){--a->readers;--b->readers;--p->readers;--o->writers;}}done{a,b,o,p};
            std::this_thread::sleep_for(std::chrono::microseconds(50+lane*35));
            for(unsigned t=0;t<l;++t)for(unsigned j=0;j<n;++j){
                unsigned __int128 sums[3]{};
                for(unsigned z=0;z<count;++z){
                    const size_t at=((size_t(z)*l+t)*(2*n)+lane*n+j)*2;
                    require(at+1<a->dev.size()&&at+1<b->dev.size(),"model canonical input bounds");
                    sums[0]+=(unsigned __int128)a->dev[at]*b->dev[at];
                    sums[1]+=(unsigned __int128)a->dev[at]*b->dev[at+1]+(unsigned __int128)a->dev[at+1]*b->dev[at];
                    sums[2]+=(unsigned __int128)a->dev[at+1]*b->dev[at+1];
                }
                require(p->dev[t*4]>1,"model parameter sync missing");
                for(unsigned c=0;c<3;++c)o->dev[(size_t(t)*n+j)*3+c]=uint64_t(sums[c]%p->dev[t*4]);
            }
            if(corrupt)o->dev[0]^=1;
        });
    }
    void abort(){if(work.valid())work.wait();}
    void wait(){if(work.valid())work.get();}
};
}
constexpr int XCL_BO_SYNC_BO_TO_DEVICE=0,XCL_BO_SYNC_BO_FROM_DEVICE=1;
struct Kernels {
    xrt::kernel reader,reducer;
    Kernels(const xrt::device&,const xrt::uuid&,unsigned lane):reader{true,lane},reducer{false,lane}{}
};
inline void wait_for_run(const char*,xrt::run& run,Clock::time_point){run.wait();}
