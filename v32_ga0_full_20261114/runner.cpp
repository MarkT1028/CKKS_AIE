#include <cstring>
#include <sys/resource.h>
#ifdef GA_RESIDENT_MODEL
#define CKKSMAC_PARSER_ONLY
#endif
#define FULL_HS4_BACKEND_ONLY
#include <variants/v32_native_pl_2_pipe/host/bo_host.cpp>
#undef FULL_HS4_BACKEND_ONLY
#include <common/finish_overlap.hpp>
#ifdef GA_RESIDENT_MODEL
#include <tests/mock_xrt.hpp>
#endif
#include <wire.hpp>
#include "../v32_ga3_finishopt_20261110/common/sealed_sha256.hpp"
#include "ga0.hpp"

namespace ga_resident {
using ga::check;
struct Window { std::vector<ga::Tile> tiles; };
struct Source {
    std::array<std::vector<uint64_t>, ga::weight_slots> weights;
    std::vector<uint64_t> baby;
    std::vector<std::string> output_hashes;
};
}
#include "../v32_ga_resident_20261114/backend.hpp"

namespace {
using ga::check;
using namespace ga0;
using boexp::Clock;

class Fixture {
    const fs::path root;
    const finishsha::Engine& hash;
    std::map<std::string,std::string> digests;
public:
    double read_ms=0, hash_ms=0;
    uint64_t read_bytes=0;

    Fixture(fs::path path,const finishsha::Engine& engine) : root(std::move(path)),hash(engine) {
        std::ifstream index(root/"INDEX.tsv");
        std::string key,digest;
        while(index>>key>>digest)
            check(digest.size()==64&&digests.emplace(key,digest).second,"bad fixture index");
        check(index.eof() && digests.size()==Groups*Blocks*(Ring/N)+OutputCount*Groups+2,
              "fixture index count");
    }

    template<class T> void load(const std::string& name,std::vector<T>& values,size_t count) {
        const auto path=root/name;
        check(fs::is_regular_file(path)&&!fs::is_symlink(path)&&fs::file_size(path)==count*sizeof(T),
              ("fixture size differs: "+name).c_str());
        values.resize(count);
        std::ifstream file(path,std::ios::binary);
        auto start=Clock::now();
        file.read(reinterpret_cast<char*>(values.data()),count*sizeof(T));
        check(bool(file),"truncated fixture");
        read_ms+=boexp::elapsed(start,Clock::now());
        start=Clock::now();
        check(hash.hex(nullptr,0,values.data(),count*sizeof(T))==digests.at(name),
              ("fixture SHA256 differs: "+name).c_str());
        hash_ms+=boexp::elapsed(start,Clock::now());
        read_bytes+=count*sizeof(T);
    }

    std::istringstream text(const std::string& name) {
        const auto path=root/name;
        check(fs::is_regular_file(path)&&fs::file_size(path)<2*1024*1024,"text fixture size");
        std::vector<char> bytes;
        load(name,bytes,fs::file_size(path));
        return std::istringstream(std::string(bytes.begin(),bytes.end()));
    }
};

void run(const fs::path& xclbin,const fs::path& marker,const fs::path& data,
         const fs::path& result,const std::string& scope) {
    check(scope=="smoke"||scope=="full","expected smoke or full");
    check(!fs::exists(marker)&&fs::is_directory(result),"recovery marker or result directory");
    const auto setup_start=Clock::now();
    finishsha::Engine hash;
    Fixture fixture(data,hash);
    ga_resident::Source inputs;
    std::array<uint64_t,Towers> moduli{}, roots{};
    auto basis=fixture.text("basis.txt");
    auto gold=fixture.text("expected.txt");
    std::string extra;
    for(unsigned t=0;t<Towers;++t)
        check(bool(basis>>moduli[t]>>roots[t])&&moduli[t]>=(1ULL<<44)&&moduli[t]<(1ULL<<60)
              &&moduli[t]%2&&roots[t]>1&&roots[t]<moduli[t],"invalid RNS basis");
    check(!(basis>>extra),"extra RNS moduli");
    inputs.output_hashes.resize(Tiles);
    for(auto& digest:inputs.output_hashes)
        check(bool(gold>>digest)&&digest.size()==64,"invalid expected digest");
    check(!(gold>>extra),"extra expected digests");
    fixture.read_ms=fixture.hash_ms=0;
    fixture.read_bytes=0;
#ifdef GA_RESIDENT_MODEL
    xrt::device device;
    xrt::uuid uuid;
    const char* backend_name="xrt_contract_model";
#else
    validate_boot_xclbin(xclbin);
    validate_boot_marker();
    xrt::ini::set("Runtime.enable_flat","false");
    xrt::ini::set("Runtime.force_program_xclbin","false");
    xrt::ini::set("Runtime.ert_polling","true");
    xrt::ini::set("Runtime.xgq_polling","true");
    auto device=xrt::device(0);
    auto uuid=device.load_xclbin(xclbin.string());
    const char* backend_name="pure_pl";
#endif
    ga_resident::Backend backend(device,uuid,1,hash,inputs,true);
    std::array<std::vector<int64_t>,OutputCount> compact;
    std::array<std::vector<uint64_t>,OutputCount> plain;
    std::ofstream trace(result/"tiles.csv");
    check(bool(trace),"cannot open tile evidence");
    trace<<"tile,output,group,tower,L,coefficient,sha256,resident_ms,weight_copy_sync_ms,baby_copy_sync_ms,execute_ms,output_sha256_ms\n"
         <<std::setprecision(12);
    const double setup=boexp::elapsed(setup_start,Clock::now());
    const auto request_start=Clock::now();
    double expand=0,resident=0,slice=0;
    unsigned count=0;
    uint64_t words=0,uploaded_bytes=0;
    const bool full=scope=="full";
    for(unsigned g=0;g<Groups;++g) for(unsigned r=0;r<Blocks;++r) {
        if(!full && r!=0 && r!=Blocks-1)continue;
        const unsigned l=tower_count(r), tower=r*L;
        auto tick=Clock::now();
        std::vector<Transform> transforms;
        for(unsigned t=0;t<l;++t)transforms.emplace_back(moduli[tower+t],roots[tower+t]);
        expand+=boexp::elapsed(tick,Clock::now());
        for(unsigned o=0;o<OutputCount;++o) {
            if(!full && o!=0 && o!=OutputCount-1)continue;
            if(r==0) fixture.load(name('p',o,g),compact[o],size_t(K)*Ring);
            tick=Clock::now();
            auto& packed=plain[o];
            packed.resize(size_t(K)*l*Ring);
            for(unsigned k=0;k<K;++k)
                for(unsigned t=0;t<l;++t)
                    transforms[t].forward(compact[o].data()+size_t(k)*Ring,
                                            packed.data()+(size_t(k)*l+t)*Ring);
            expand+=boexp::elapsed(tick,Clock::now());
        }
        for(unsigned c=0;c<Ring/N;++c) {
            if(!full && c!=0 && c!=Ring/N-1)continue;
            fixture.load(name('a',g,r,c),inputs.weights[0],size_t(K)*l*N*2);
            ga::Tile tile{id(g,r,c,0),N,l,K,0,0,
                          {moduli.begin()+tower,moduli.begin()+tower+l}};
            tile.validate();
            ga::input_range(tile,inputs.weights[0].data());
            for(unsigned o=0;o<OutputCount;++o) {
                if(!full && o!=0 && o!=OutputCount-1)continue;
                tile.id=id(g,r,c,o);
                tile.flags=o?ga::reuse_weight:0;
                tick=Clock::now();
                inputs.baby.resize(tile.input_words());
                for(unsigned k=0;k<K;++k) for(unsigned t=0;t<l;++t) {
                    const size_t block=size_t(k)*l+t;
                    const auto* from=plain[o].data()+block*Ring+c*N;
                    auto* to=inputs.baby.data()+block*N*2;
                    for(unsigned j=0;j<N;++j) {
                        to[2*j]=from[j];
                        to[2*j+1]=0;
                    }
                }
                slice+=boexp::elapsed(tick,Clock::now());
                ga_resident::Window window{{tile}};
                if(o==0) {
                    std::ofstream active(marker);
                    active<<"PL block "<<g<<'/'<<r<<'/'<<c<<'\n';
                    active.close();
                    check(bool(active),"cannot write recovery marker");
                }
                boexp::Frame frame;
                tick=Clock::now();
                backend.configure(window);
                try {
                    backend.prepare(0,0,frame,tick);
                    frame.timed("execute",-1,tick,[&]{backend.start(0,0);backend.wait(0,0);});
                    backend.complete(0,0,frame,tick);
                    backend.finish(0,0,frame,tick);
                } catch(...) {
                    backend.cancel();
                    throw;
                }
                const double elapsed=boexp::elapsed(tick,Clock::now());
                resident+=elapsed;
                ++count;
                words+=tile.output_words();
                uploaded_bytes+=tile.input_words()*8*(o?1:2);
                trace<<tile.id<<','<<o<<','<<g<<','<<tower<<','<<l<<','<<c*N<<','
                     <<backend.digests[0]<<','<<elapsed;
                for(const char* stage:{"weight_copy_sync","baby_copy_sync","execute","output_sha256"})
                    trace<<','<<frame.total(stage);
                trace<<'\n';
            }
            check(fs::remove(marker),"cannot remove recovery marker");
        }
        trace.flush();
        check(bool(trace),"persist evidence");
        std::cout<<"GA0_PROGRESS group="<<g<<" tower="<<tower<<" tiles="<<count<<std::endl;
    }
    const double request=boexp::elapsed(request_start,Clock::now());
    check(count==(full?Tiles:32) && (!full || words==Words),"incomplete scope");
    struct rusage usage{};
    check(::getrusage(RUSAGE_SELF,&usage)==0,"resource stats");
    trace.close();
    check(bool(trace),"close tile evidence");
    std::ofstream summary(result/"native.json");
    summary<<std::setprecision(12)<<"{\n\"backend\":\""<<backend_name<<"\",\n"
           <<"\"tiles\":"<<count<<",\n\"verified_words\":"<<words
           <<",\n\"uploaded_bytes\":"<<uploaded_bytes<<",\n\"read_bytes\":"<<fixture.read_bytes
           <<",\n\"read_ms\":"<<fixture.read_ms<<",\n\"input_sha256_ms\":"<<fixture.hash_ms
           <<",\n\"ntt_ms\":"<<expand<<",\n\"slice_ms\":"<<slice
           <<",\n\"resident_ms\":"<<resident<<",\n\"request_ms\":"<<request
           <<",\n\"setup_ms\":"<<setup<<",\n\"peak_process_rss_kib\":"<<usage.ru_maxrss<<"\n}\n";
    summary.close();
    check(bool(summary),"close summary");
}
}

int main(int argc,char** argv) {
    try {
        ga::little_endian();
        if(argc==2&&std::string(argv[1])=="--crypto-check") {
            finishsha::Engine hash;
            std::cout<<"PASS_GA0_FULL_SHA256 "<<hash.description()<<'\n';
            return 0;
        }
        check(argc==6,"usage: ga0_full XCLBIN MARKER FIXTURE RESULTS smoke|full");
        run(argv[1],argv[2],argv[3],argv[4],argv[5]);
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"GA0_FULL_FAIL: "<<error.what()<<'\n';
        return 1;
    }
}
