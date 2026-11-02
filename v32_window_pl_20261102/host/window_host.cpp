#ifdef WINDOW_SOFTWARE_MODEL
#define CKKSMAC_PARSER_ONLY
#endif
#define FULL_HS4_BACKEND_ONLY
#if defined(WINDOW_PURE_PL) && !defined(CKKSMAC_PARSER_ONLY)
#include "../variants/v32_pure_pl_2_pipe/host/bo_host.cpp"
#else
#include "../variants/v32_core_2_pipe/host/bo_host.cpp"
#endif
#undef FULL_HS4_BACKEND_ONLY
#include "../common/mapped_source.hpp"
#include "../common/window_source.hpp"
#include "../common/io_metrics.hpp"
#include "../common/stream_output.hpp"
#include "../common/window_tasks.hpp"
#include "window_xrt.hpp"
#ifdef WINDOW_SOFTWARE_MODEL
#include "../tests/window_model.hpp"
#endif
#include "../common/window_replay.hpp"
namespace {
void check_window(const fs::path& data){windowio::Dataset source(data);streamio::Dataset old(data);source.begin_request();old.begin_request();std::array<std::vector<uint64_t>,2> lane;for(auto& v:lane)v.resize(source.input_words()/2);uint64_t checked=0;
 for(const auto& job:windowed::tasks(source.dimensions.chunks,"chunk",false)){source.cache_baby(job.chunk);std::vector<uint64_t> packed(source.input_words()/2);for(unsigned l=0;l<2;++l){source.pack_cached(job.group,job.chunk,l,2,lane[l].data(),lane[l].size(),true);old.pack(job.group,job.chunk,l,2,packed.data(),packed.size());require(packed==lane[l],"window pack differs from frozen source");}auto gold=source.expected(job.group,job.chunk);source.verify(job.group,job.chunk,gold);source.retire_job(job.group,job.chunk,false);checked+=gold.size();}source.complete_coverage();source.end_request();old.end_request();std::cout<<"PASS_WINDOW_FULL_LANE_PACK_EQUIVALENCE groups=6 verified_words="<<checked<<" no_XRT_execution=1\n";
}
}
int main(int argc,char** argv){try{
 if(argc==3&&std::string(argv[1])=="--check-data"){check_window(argv[2]);return 0;}
 bool service=argc==5&&std::string(argv[1])=="--serve";require(service||argc==9,"usage: window_host XCLBIN DATA NEW_RESULTS REPS WARMUPS descending|ascending group|chunk retain|bounded|export_bounded");fs::path xb=argv[service?2:1],data=argv[service?3:2],dir=argv[service?4:3];auto start=Clock::now();
#ifndef CKKSMAC_PARSER_ONLY
 validate_boot_xclbin(xb);validate_boot_marker();
#endif
 windowio::Dataset source(data);
#ifdef WINDOW_SOFTWARE_MODEL
 windowed::SoftwareWindowBackend backend(source);
#elif !defined(CKKSMAC_PARSER_ONLY)
 require(source.shape.n==8192&&source.shape.l==14&&source.shape.k==16&&source.dimensions.full_n==131072&&source.dimensions.chunks==16,"firmware shape requires real N131072 L14 K16");xrt::ini::set("Runtime.enable_flat","false");xrt::ini::set("Runtime.force_program_xclbin","false");xrt::ini::set("Runtime.ert_polling","true");xrt::ini::set("Runtime.xgq_polling","true");auto device=xrt::device(0);auto uuid=device.load_xclbin(xb.string());
#ifdef WINDOW_PURE_PL
 // No graph object, graph reset or graph.run in the pure-PL branch.
 windowed::XrtWindowBackend backend(device,uuid,source,nullptr);
#else
 auto graph=xrt::graph(device,uuid,"ckks_graph");graph.reset();windowed::XrtWindowBackend backend(device,uuid,source,&graph);
#endif
#else
 throw std::runtime_error("parser only, cannot execute");
#endif
#if defined(WINDOW_SOFTWARE_MODEL) || !defined(CKKSMAC_PARSER_ONLY)
 boexp::Worker worker;double setup_ms=ms(start,Clock::now());
 if(service)windowed::serve(backend,source,worker,dir);else{std::string order=argv[6];require(order=="ascending"||order=="descending","window order");windowed::run_requests(backend,source,worker,dir,number(argv[4],20),number(argv[5],3),order=="ascending",argv[7],argv[8]);}worker.close();
 std::ofstream setup(dir/"setup.json");setup<<std::setprecision(12)<<"{\"setup_ms\":"<<setup_ms<<",\"execution_backend\":\""<<decltype(backend)::execution_backend<<"\",\"AIE_compute_tiles\":"<<decltype(backend)::aie_tiles<<",\"banks\":2,\"shared_baby_cache_payload_bytes\":"<<source.cache_bytes()<<",\"merge_heap_bytes\":"<<source.shape.output_words()*8<<",\"whole_group_input_heap_bytes\":0,\"cache_copy_cost_inside_each_request\":true,\"input_sync_full_BO_preserved\":true,\"retirement_is_advisory_not_hard_RSS_limit\":true,\"buffered_output_no_fsync_guarantee\":true}\n";setup.close();require(bool(setup),"window setup write");return 0;
#endif
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
