#ifdef STREAM_SOFTWARE_MODEL
#define CKKSMAC_PARSER_ONLY
#endif
#define FULL_HS4_BACKEND_ONLY
#include "../variants/v32_core_2_pipe/host/bo_host.cpp"
#undef FULL_HS4_BACKEND_ONLY
#include "../common/mapped_source.hpp"
#include "../common/io_metrics.hpp"
#include "../common/stream_output.hpp"
#include "stream_xrt.hpp"
#ifdef STREAM_SOFTWARE_MODEL
#include "../tests/stream_model.hpp"
#endif
#include "../common/stream_replay.hpp"

namespace {
void check_stream(const fs::path& data){streamio::Dataset source(data);InputCase c;c.n=source.shape.n;c.l=source.shape.l;c.k=source.shape.k;c.parameters=source.shape.parameters;c.words.resize(source.input_words());source.begin_request();uint64_t words=0;for(unsigned g=0;g<6;++g)for(unsigned i=0;i<source.dimensions.chunks;++i){source.pack(g,i,0,1,c.words.data(),c.words.size());auto gold=source.expected(g,i);selftest(c,gold);source.verify(g,i,gold);words+=gold.size();}source.end_request();std::cout<<"PASS_STREAM_PARSER_SPLIT_MERGE groups=6 words="<<words<<" no_XRT_execution=1\n";}
}
int main(int argc,char**argv){try{
 if(argc==3&&std::string(argv[1])=="--check-data"){check_stream(argv[2]);return 0;}
 const bool serve=argc==5&&std::string(argv[1])=="--serve";require(serve||argc==7,"usage: stream_host XCLBIN DATA NEW_RESULTS REPS WARMUPS descending|ascending | --serve XCLBIN DATA NEW_SESSION_ROOT");
 fs::path xclbin=argv[serve?2:1],data=argv[serve?3:2],dir=argv[serve?4:3];auto start=Clock::now();
#ifndef CKKSMAC_PARSER_ONLY
 validate_boot_xclbin(xclbin);validate_boot_marker();
#endif
 streamio::Dataset source(data);
#ifdef STREAM_SOFTWARE_MODEL
 streaming::SoftwareStreamBackend backend(source);
#elif !defined(CKKSMAC_PARSER_ONLY)
 require(source.shape.n==8192&&source.shape.l==14&&source.shape.k==16&&source.dimensions.full_n==131072&&source.dimensions.chunks==16,"current firmware requires real N131072 L14 K16 fixture");xrt::ini::set("Runtime.enable_flat","false");xrt::ini::set("Runtime.force_program_xclbin","false");xrt::ini::set("Runtime.ert_polling","true");xrt::ini::set("Runtime.xgq_polling","true");auto device=xrt::device(0);auto uuid=device.load_xclbin(xclbin.string());auto graph=xrt::graph(device,uuid,"ckks_graph");graph.reset();streaming::XrtStreamBackend backend(device,uuid,graph,source);
#else
 throw std::runtime_error("parser-only build; no hardware or software execution");
#endif
#if defined(STREAM_SOFTWARE_MODEL) || !defined(CKKSMAC_PARSER_ONLY)
 boexp::Worker worker;double setup_ms=ms(start,Clock::now());require(!fs::exists(dir),"stream output directory exists");if(serve){streaming::fixture_service(backend,source,worker,dir);}else{std::string order=argv[6];require(order=="descending"||order=="ascending","stream order");streaming::run_requests(backend,source,worker,dir,number(argv[4],20),number(argv[5],3),order=="ascending");}worker.close();
 std::ofstream setup(dir/"setup.json");setup<<std::setprecision(12)<<"{\"setup_ms\":"<<setup_ms<<",\"execution_backend\":\""<<decltype(backend)::execution_backend<<"\",\"AIE\":2,\"banks\":2,\"whole_group_input_heap_bytes\":0,\"merge_heap_bytes\":"<<source.shape.output_words()*8<<",\"shared_validation_in_each_request\":true,\"mmap_RSS_is_not_bounded_by_heap_size\":true,\"fixture_service\":"<<serve<<"}\n";setup.close();require(bool(setup),"stream setup write");return 0;
#endif
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
