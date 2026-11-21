#include <cstring>
#include "../common/input_stream.hpp"
#include "../common/profile.hpp"
#include <sys/resource.h>
#ifdef GA_RESIDENT_MODEL
#define CKKSMAC_PARSER_ONLY
#endif
#define FULL_HS4_BACKEND_ONLY
#include <variants/v32_native_pl_2_pipe/host/bo_host.cpp>
#undef FULL_HS4_BACKEND_ONLY
#include "../common/three_bank.hpp"
#ifdef GA_RESIDENT_MODEL
#include "mock_xrt.hpp"
#endif
#include <wire.hpp>
#include "../../v32_ga3_finishopt_20261110/common/sealed_sha256.hpp"
#include "../../v32_ga0_full_20261114/ga0.hpp"
#include "ntt.hpp"

namespace ga_resident {
using ga::check;
struct Window { std::vector<ga::Tile> tiles; };
struct Source {
    std::array<std::vector<uint64_t>, ga::weight_slots> weights;
    std::vector<std::string> output_hashes;
};
}
#include "backend.hpp"

namespace {
using ga::check;
using namespace ga0;
using boexp::Clock;

struct ReadStats {
    double read_ms = 0, hash_ms = 0;
    uint64_t read_bytes = 0;

    void add(const ReadStats& stats) {
        read_ms += stats.read_ms;
        hash_ms += stats.hash_ms;
        read_bytes += stats.read_bytes;
    }
};

class Fixture {
    const fs::path root;
    const finishsha::Engine& hash;
    std::map<std::string,std::string> digests;
public:
    ReadStats stats;

    Fixture(fs::path path,const finishsha::Engine& engine) : root(std::move(path)),hash(engine) {
        std::ifstream index(root/"INDEX.tsv");
        std::string key,digest;
        while(index>>key>>digest)
            check(digest.size()==64&&digests.emplace(key,digest).second,"bad fixture index");
        check(index.eof() && digests.size()==Groups*Blocks*(Ring/N)+OutputCount*Groups+2,
              "fixture index count");
    }

    template<class T> ReadStats read(const std::string& name,std::vector<T>& values,size_t count) const {
        const auto path=root/name;
        const size_t size = count*sizeof(T);
        const bool remote = ga_stream::enabled() && name.rfind("data/", 0) == 0;
        if (!remote) check(fs::is_regular_file(path)&&!fs::is_symlink(path)&&fs::file_size(path)==size,
                           ("fixture size differs: "+name).c_str());
        values.resize(count);
        auto start=Clock::now();
        if (remote) {
            ga_stream::fetch("ga0", name, {{values.data(), size}});
        } else {
            std::ifstream file(path,std::ios::binary);
            file.read(reinterpret_cast<char*>(values.data()), size);
            check(bool(file),"truncated fixture");
        }
        const double read = boexp::elapsed(start,Clock::now());
        start=Clock::now();
        check(hash.hex(nullptr,0,values.data(),size)==digests.at(name),
              ("fixture SHA256 differs: "+name).c_str());
        return {read, boexp::elapsed(start,Clock::now()), size};
    }

    template<class T> void load(const std::string& name,std::vector<T>& values,size_t count) {
        stats.add(read(name, values, count));
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
    fixture.stats = {};
#ifdef GA_RESIDENT_MODEL
    xrt::device device;
    xrt::uuid uuid;
    const char* backend_name="xrt_contract_model";
    xrt::corrupt_output = std::getenv("GA_CTPT_TEST_CORRUPT_OUTPUT") != nullptr;
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
    std::array<std::unique_ptr<LazyTransform<Ring>>, Towers> plans;
    boexp::Worker ntt_worker;
    boexp::Worker plaintext_worker;
    const bool overlap = ga_opt::fast_profile();
    const char* ntt_setting=std::getenv("V32_GA0_NTT_BLOCK");
    const std::string block_arg=ntt_setting ? ntt_setting : "1024";
    check(block_arg=="512" || block_arg=="1024" || block_arg=="2048","invalid NTT block size");
    const unsigned ntt_block=std::stoul(block_arg);
    const bool read_ahead = overlap && ga_opt::read_ahead_allowed();
    std::array<std::vector<uint64_t>,Ring/N> prefetched;
    ReadStats prefetch_stats;
    std::mutex ready_mutex;
    std::condition_variable ready;
    unsigned ready_count = 0;
    std::exception_ptr read_fault;
    double prefetch_work = 0, prefetch_wait = 0;
    unsigned prefetched_blocks = 0;
    // The worker is destroyed before the buffers and statistics it owns.
    std::unique_ptr<boexp::Worker> weight_worker;
    if (read_ahead) weight_worker = std::make_unique<boexp::Worker>();
    std::ofstream trace(result/"tiles.csv");
    std::ofstream batches(result/"windows.csv");
    check(bool(trace)&&bool(batches),"cannot open replay evidence");
    trace<<"tile,output,group,tower,L,coefficient,sha256,weight_copy_sync_ms,baby_copy_sync_ms,execute_ms,output_sha256_ms,baby_pack_ms,status_ms,output_sync_ms,prepare_lane_ms\n"
         <<std::setprecision(12);
    batches<<"group,tower,coefficient,tiles,wall_ms,resident_start_ms,resident_end_ms\n"<<std::setprecision(12);
    const double setup=boexp::elapsed(setup_start,Clock::now());
    const auto request_start=Clock::now();
    double expand=0,resident=0,slice=0;
    unsigned count=0;
    uint64_t words=0,uploaded_bytes=0, device_readback_bytes=0;
    const bool full=scope=="full";
    for(unsigned g=0;g<Groups;++g) for(unsigned r=0;r<Blocks;++r) {
        if(!full && r!=0 && r!=Blocks-1)continue;
        const unsigned l=tower_count(r), tower=r*L;
        if (read_ahead) {
            const unsigned last = Ring/N - 1;
            ready_count = 0;
            read_fault = nullptr;
            weight_worker->submit([&, g, r, l, full, last] {
              try {
                const auto start = Clock::now();
                prefetch_stats = {};
                for (unsigned c = 0; c < Ring/N; ++c) {
                    if (!full && c != 0 && c != last) continue;
                    prefetch_stats.add(fixture.read(name('a',g,r,c), prefetched[c], size_t(K)*l*N*2));
                    {
                        std::lock_guard<std::mutex> lock(ready_mutex);
                        ready_count = c + 1;
                    }
                    ready.notify_one();
                }
                prefetch_work += boexp::elapsed(start, Clock::now());
              } catch (...) {
                {
                    std::lock_guard<std::mutex> lock(ready_mutex);
                    read_fault = std::current_exception();
                }
                ready.notify_one();
                throw;
              }
            });
        }
        auto tick=Clock::now();
        for (unsigned t = 0; t < l; ++t) {
            if (!plans[tower + t]) {
                plans[tower + t] = std::make_unique<LazyTransform<Ring>>(moduli[tower + t], roots[tower + t]);
            }
        }
        expand+=boexp::elapsed(tick,Clock::now());
        for(unsigned o=0;o<OutputCount;++o) {
            if(!full && o!=0 && o!=OutputCount-1)continue;
            if(r==0) fixture.load(name('p',o,g),compact[o],size_t(K)*Ring);
            tick=Clock::now();
            auto& packed=plain[o];
            packed.resize(size_t(K)*l*Ring);
            const auto* coefficients = compact[o].data();
            auto* target = packed.data();
            auto transform_half = [&](unsigned parity) {
                for (unsigned k = parity; k < K; k += 2) {
                    for (unsigned t = 0; t < l; ++t) {
                        plans[tower + t]->forward(coefficients + size_t(k) * Ring,
                                                   target + (size_t(k) * l + t) * Ring, overlap,ntt_block);
                    }
                }
            };
            ntt_worker.submit([&] { transform_half(1); });
            try { transform_half(0); }
            catch (...) { ntt_worker.close(); throw; }
            ntt_worker.wait();
            expand+=boexp::elapsed(tick,Clock::now());
        }
        for(unsigned c=0;c<Ring/N;++c) {
            if(!full && c!=0 && c!=Ring/N-1)continue;
            if (read_ahead) {
                tick = Clock::now();
                std::unique_lock<std::mutex> lock(ready_mutex);
                ready.wait(lock, [&] { return read_fault || ready_count > c; });
                if (read_fault) std::rethrow_exception(read_fault);
                inputs.weights[0].swap(prefetched[c]);
                prefetch_wait += boexp::elapsed(tick,Clock::now());
            }
            else fixture.load(name('a',g,r,c),inputs.weights[0],size_t(K)*l*N*2);
            const ga::Tile first{id(g,r,c,0),N,l,K,0,0,
                                 {moduli.begin()+tower,moduli.begin()+tower+l}};
            first.validate();
            ga::input_range(first,inputs.weights[0].data());
            std::vector<unsigned> outputs;
            ga_resident::Window window;
            for(unsigned o=0;o<OutputCount;++o) {
                if(!full && o!=0 && o!=OutputCount-1)continue;
                auto tile = first;
                tile.id=id(g,r,c,o);
                tile.flags=o?ga::reuse_weight:0;
                outputs.push_back(o);
                window.tiles.push_back(std::move(tile));
            }
            tick=Clock::now();
            backend.set_baby_writer([&plain, &outputs, l, c](unsigned index, uint64_t* to, size_t words) {
                    check(words == size_t(K) * l * N, "compact plaintext BO packing span");
                    const auto* plane = plain.at(outputs.at(index)).data();
                    for (size_t block = 0; block < size_t(K) * l; ++block) {
                        const auto* from = plane + block * Ring + c * N;
                        std::memcpy(to, from, N * sizeof(uint64_t));
                        to += N;
                    }
            });
            slice+=boexp::elapsed(tick,Clock::now());
            {
                std::ofstream active(marker);
                active<<"PL block "<<g<<'/'<<r<<'/'<<c<<'\n';
                active.close();
                check(bool(active),"cannot write recovery marker");
            }
            tick=Clock::now();
            backend.configure(window);
            boexp::Replay replay;
            if (overlap) {
                replay=boexp::run_three_bank(backend,unsigned(window.tiles.size()),plaintext_worker,false);
            } else {
                replay.frames.resize(window.tiles.size());
                try {
                    for (unsigned i=0;i<window.tiles.size();++i) {
                        auto& frame=replay.frames[i];
                        backend.prepare(i,0,frame,tick);
                        frame.timed("execute",-1,tick,[&]{backend.start(i,0);backend.wait(i,0);});
                        backend.complete(i,0,frame,tick);
                        backend.finish(i,0,frame,tick);
                    }
                } catch(...) {
                    backend.cancel();
                    throw;
                }
            }
            const double elapsed=boexp::elapsed(tick,Clock::now());
            resident+=elapsed;
            batches<<g<<','<<tower<<','<<c*N<<','<<window.tiles.size()<<','<<elapsed<<','
                   <<boexp::elapsed(request_start,tick)<<','<<boexp::elapsed(request_start,tick)+elapsed<<'\n';
            for(unsigned i=0;i<outputs.size();++i) {
                const auto& tile=window.tiles[i];
                const auto& frame=replay.frames[i];
                const unsigned o=outputs[i];
                ++count;
                words+=tile.output_words();
                uploaded_bytes+=tile.input_words()*8*(o?1:3)/2;
                device_readback_bytes+=uint64_t(tile.n)*tile.l*2*sizeof(uint64_t);
                trace<<tile.id<<','<<o<<','<<g<<','<<tower<<','<<l<<','<<c*N<<','
                     <<backend.digests[i];
                for(const char* stage:{"weight_copy_sync","baby_copy_sync","execute","output_sha256","baby_pack","status","output_sync","prepare_lane"})
                    trace<<','<<frame.total(stage);
                trace<<'\n';
            }
            check(fs::remove(marker),"cannot remove recovery marker");
        }
        if (read_ahead) {
            weight_worker->wait();
            fixture.stats.add(prefetch_stats);
            ++prefetched_blocks;
        }
        trace.flush();
        batches.flush();
        check(bool(trace)&&bool(batches),"persist evidence");
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
           <<"\"host_profile\":\""<<(overlap?"fast":"baseline")<<"\",\n"
           <<"\"input_source\":\""<<(ga_stream::enabled()?"net":"sd")<<"\",\n"
           <<"\"ntt_fused_stages\":"<<(overlap?"true":"false")<<",\n"
           <<"\"plaintext_pipeline\":"<<(overlap?"true":"false")<<",\n"
           <<"\"weight_prefetch_enabled\":"<<(read_ahead?"true":"false")<<",\n"
           <<"\"prefetched_weight_blocks\":"<<prefetched_blocks<<",\n"
           <<"\"weight_prefetch_work_ms\":"<<prefetch_work<<",\n"
           <<"\"weight_prefetch_wait_ms\":"<<prefetch_wait<<",\n"
           <<"\"packing_in_resident\":true,\n"
           <<"\"ntt_workers\":2,\n"
           <<"\"ntt_block_coefficients\":"<<ntt_block<<",\n"
           <<"\"tiles\":"<<count<<",\n\"verified_words\":"<<words
           <<",\n\"uploaded_bytes\":"<<uploaded_bytes<<",\n\"read_bytes\":"<<fixture.stats.read_bytes
           <<",\n\"device_readback_bytes\":"<<device_readback_bytes
           <<",\n\"read_ms\":"<<fixture.stats.read_ms<<",\n\"input_sha256_ms\":"<<fixture.stats.hash_ms
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
            std::cout<<"PASS_GA0_CTPT_SHA256 "<<hash.description()<<'\n';
            return 0;
        }
        check(argc==6,"usage: ga0_ctpt XCLBIN MARKER FIXTURE RESULTS smoke|full");
        run(argv[1],argv[2],argv[3],argv[4],argv[5]);
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"GA0_CTPT_FAIL: "<<error.what()<<'\n';
        return 1;
    }
}
