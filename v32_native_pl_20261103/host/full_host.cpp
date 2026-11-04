// Keep the proven two-bank finish-overlap implementation and all UUID guards.
#define FULL_HS4_BACKEND_ONLY
#include "../variants/v32_core_2_pipe/host/bo_host.cpp"
#undef FULL_HS4_BACKEND_ONLY
#include "../common/compact_dataset.hpp"
namespace {
void check_full(const fs::path& root){CachedDataset c;std::vector<Parameter> parameters;uint64_t verified=0;
 for(int group=5;group>=0;--group){load_compact_group(c,root,group);for(const auto& chunk:c.chunks){selftest(chunk.input,chunk.expected);verified+=chunk.expected.size();}if(group==5)parameters=c.chunks.front().input.parameters;else require(parameters.size()==c.chunks.front().input.parameters.size(),"group modulus coverage");std::cout<<"PASS_COMPACT_GROUP group="<<group<<" chunks="<<c.chunks.size()<<" words="<<c.golden_bytes/8<<'\n'<<std::flush;}
 std::cout<<"PASS_ALL_SIX_GROUPS words="<<verified<<" fixture_only_no_XRT=true\n";
}
#ifndef CKKSMAC_PARSER_ONLY
void full_host(const fs::path& xclbin,const fs::path& root,const fs::path& dir,unsigned reps,unsigned warm,bool reverse,const std::string& mode){
 require(reps>=1&&reps<=20&&warm<=3,"full replay counts");require(mode=="map_pingpong"||mode=="map_finish_overlap","full replay mode");require(!fs::exists(dir),"result directory exists");
 auto setup_begin=Clock::now();CachedDataset cache;load_compact_group(cache,root,5);const auto n=cache.chunks.front().input.n,l=cache.chunks.front().input.l,k=cache.chunks.front().input.k;const auto chunks=cache.chunks.size();require(n==8192&&l==14&&k==16&&chunks==16,"real full layer requires16 N8192 L14 K16 chunks per group");
 validate_boot_xclbin(xclbin);validate_boot_marker();fs::create_directories(dir/"outputs");
 xrt::ini::set("Runtime.enable_flat","false");xrt::ini::set("Runtime.force_program_xclbin","false");xrt::ini::set("Runtime.ert_polling","true");xrt::ini::set("Runtime.xgq_polling","true");
 auto device=xrt::device(0);auto uuid=device.load_xclbin(xclbin.string());auto graph=xrt::graph(device,uuid,"ckks_graph");graph.reset();
 // Construct ONCE, outside iterations, then retain device/graph/kernels/BOs and
 // the prep worker across all six groups. Cache changes only between replays.
 XrtBackend backend(device,uuid,graph,cache,true,2,dir/"outputs",mode=="map_finish_overlap");boexp::Worker worker;
 std::ofstream setup(dir/"setup.json");setup<<std::setprecision(12)<<"{\"setup_ms\":"<<ms(setup_begin,Clock::now())<<",\"banks\":2,\"AIE\":2,\"one_group_cache\":true,\"firmware_changed\":false}\n";setup.close();require(bool(setup),"setup write");
 std::ofstream groups(dir/"groups.csv"),whole(dir/"iterations.csv"),timeline(dir/"timeline.csv");groups<<std::fixed<<std::setprecision(6);whole<<std::fixed<<std::setprecision(6);timeline<<std::fixed<<std::setprecision(6);
 groups<<"repetition,warmup,export_only,ordinal,group,admission_ms,resident_verified_wall_ms,host_execute_envelope_sum_ms,output_save_work_ms,verified_words\n";
 whole<<"repetition,warmup,export_only,groups,full_six_streamed_wall_ms,admission_sum_ms,resident_wall_sum_ms,host_execute_envelope_sum_ms,verified_words\n";
 timeline<<"repetition,warmup,export_only,group,chunk,bank,stage,lane,begin_ms,end_ms\n";std::vector<double> walls,residents;
 try{for(unsigned rep=0;rep<reps+warm+1;++rep){bool exporting=rep==reps+warm,iswarm=rep<warm;auto start=Clock::now();double admission=0,resident=0,envelope=0;uint64_t verified=0;std::ostringstream grows,trows;grows<<std::fixed<<std::setprecision(6);trows<<std::fixed<<std::setprecision(6);std::vector<boexp::Replay> traces;std::vector<unsigned> trace_groups;traces.reserve(6);trace_groups.reserve(6);
  for(unsigned ordinal=0;ordinal<6;++ordinal){unsigned g=reverse?ordinal:5-ordinal;auto load_start=Clock::now();load_compact_group(cache,root,g);require(cache.chunks.size()==chunks&&cache.chunks.front().input.n==n&&cache.chunks.front().input.l==l&&cache.chunks.front().input.k==k,"group shape changed after BO allocation");double loaded=ms(load_start,Clock::now());admission+=loaded;
   auto output=dir/"outputs"/("group_"+std::to_string(g));if(exporting)fs::create_directories(output);backend.set_output_directory(output);
   auto result=mode=="map_finish_overlap"?boexp::run_finish_overlap(backend,chunks,worker,exporting):boexp::run(backend,chunks,&worker,exporting);double run=0,save=0;
   for(const auto& frame:result.frames)for(unsigned j=0;j<frame.count;++j){const auto&s=frame.spans[j];if(std::string(s.name)=="execute")run+=s.end-s.begin;if(std::string(s.name)=="output_save")save+=s.end-s.begin;}
   resident+=result.wall_ms;envelope+=run;verified+=cache.golden_bytes/8;grows<<rep<<','<<iswarm<<','<<exporting<<','<<ordinal<<','<<g<<','<<loaded<<','<<result.wall_ms<<','<<run<<','<<save<<','<<cache.golden_bytes/8<<'\n';trace_groups.push_back(g);traces.push_back(std::move(result));
  }
  double wall=ms(start,Clock::now());
  // Format and flush the detailed trace AFTER the primary full-six wall ends.
  for(unsigned ti=0;ti<traces.size();++ti)for(const auto& frame:traces[ti].frames)for(unsigned j=0;j<frame.count;++j){const auto&s=frame.spans[j];trows<<rep<<','<<iswarm<<','<<exporting<<','<<trace_groups[ti]<<','<<frame.chunk<<','<<frame.bank<<','<<s.name<<','<<s.lane<<','<<s.begin<<','<<s.end<<'\n';}
  require(verified==uint64_t(6)*131072*14*3,"full-layer MAC coverage");groups<<grows.str();timeline<<trows.str();whole<<rep<<','<<iswarm<<','<<exporting<<",6,"<<wall<<','<<admission<<','<<resident<<','<<envelope<<','<<verified<<'\n';groups.flush();timeline.flush();whole.flush();require(bool(groups)&&bool(timeline)&&bool(whole),"full replay CSV write");
  if(!iswarm&&!exporting){walls.push_back(wall);residents.push_back(resident);}std::cout<<"PASS_FULL_HS4_SIX_MAC_REPLAY repetition="<<rep<<" warmup="<<iswarm<<" export_only="<<exporting<<" full_six_streamed_wall_ms="<<wall<<" verified_words="<<verified<<'\n'<<std::flush;
 }}catch(...){backend.cancel();worker.close();throw;}worker.close();
 std::ofstream summary(dir/"summary.json");summary<<std::setprecision(12)<<"{\"status\":\"PASS_FULL_SIX_MAC_GROUPS_PENDING_GROUND_LAYER_RETURN\",\"measured\":"<<reps<<",\"warmups\":"<<warm<<",\"export_replays\":1,\"groups\":6,\"full_six_streamed_wall_median_ms\":"<<median(walls)<<",\"resident_verified_wall_sum_median_ms\":"<<median(residents)<<",\"includes_group_admission\":true,\"excludes_setup_and_export\":true,\"scope\":\"All96 ciphertext products,6 exact raw MAC groups; im2col, rotations, relinearization, aggregation,bias and downstream remain ground-side and are independently verified after download. This wall is NOT full h_s.4 end-to-end latency. Host execute envelopes are NOT pure device time.\",\"firmware_changed\":false}\n";summary.close();require(bool(summary),"full summary write");
}
#endif
}
int main(int argc,char**argv){try{
 if(argc==3&&std::string(argv[1])=="--check-data"){check_full(argv[2]);return 0;}
#ifndef CKKSMAC_PARSER_ONLY
 require(argc==8,"usage: full_host XCLBIN COMPACT_FIXTURE NEW_RESULTS REPS WARMUPS descending|ascending map_pingpong|map_finish_overlap");std::string order=argv[6];require(order=="descending"||order=="ascending","group order");full_host(argv[1],argv[2],argv[3],number(argv[4],20),number(argv[5],3),order=="ascending",argv[7]);return 0;
#else
 throw std::runtime_error("parser-only build; no XRT execution");
#endif
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
