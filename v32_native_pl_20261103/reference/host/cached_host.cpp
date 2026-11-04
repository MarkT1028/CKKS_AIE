// Reuse the validated XRT ABI, lane sharding, timeouts and boot UUID guards.
#define PERF_HOST_NO_MAIN
#include "perf_host.cpp"
#include "../common/dataset_cache.hpp"
#ifndef CKKSMAC_PARSER_ONLY
static void tiled(const fs::path& xclbin,const fs::path& root,const fs::path& dir,unsigned reps,unsigned warm,const std::string& split){
 require(reps>=1&&reps<=100&&warm<=10,"repetition count");require(!fs::exists(dir),"result directory exists");require(split=="scalar"||split=="block","invalid split mode");auto session_entry=Clock::now();CachedDataset cache(root);auto loaded_once=Clock::now();
 validate_boot_xclbin(xclbin);validate_boot_marker();fs::create_directories(dir/"outputs");
 auto session_begin=Clock::now();xrt::ini::set("Runtime.enable_flat","false");xrt::ini::set("Runtime.force_program_xclbin","false");xrt::ini::set("Runtime.ert_polling","true");xrt::ini::set("Runtime.xgq_polling","true");
 auto device=xrt::device(0);auto uuid=device.load_xclbin(xclbin.string());auto graph=xrt::graph(device,uuid,"ckks_graph");graph.reset();auto initialized=Clock::now();
 std::vector<std::unique_ptr<Lane>> lanes;
 const auto& first=cache.chunks.front().input;
 for(unsigned lane=0;lane<2;++lane)lanes.emplace_back(new Lane(device,uuid,shard(first,lane),lane));
 std::vector<uint64_t> out(first.output_words());auto ready=Clock::now();
 std::ofstream setup(dir/"setup.json");setup<<std::setprecision(12)<<"{\"dataset_load_ms\":"<<ms(session_entry,loaded_once)<<",\"xrt_init_ms\":"<<ms(session_begin,initialized)<<",\"buffer_setup_ms\":"<<ms(initialized,ready)<<",\"setup_ms\":"<<ms(session_entry,ready)<<",\"input_bytes\":"<<cache.input_bytes<<",\"golden_bytes\":"<<cache.golden_bytes<<",\"split\":\""<<split<<"\",\"ordinary_host_ram\":true}\n";setup.close();require(bool(setup),"setup write");
 std::ofstream csv(dir/"chunks.csv"),whole(dir/"iterations.csv");csv<<std::fixed<<std::setprecision(6);whole<<std::fixed<<std::setprecision(6);
 csv<<"repetition,warmup,chunk,cache_select_ms,prepare_ms,upload_poison_ms,execution_ms,status_ms,readback_merge_ms,validation_ms,transaction_ms,output_save_ms,verified_words\n";
 whole<<"repetition,warmup,chunks,execution_sum_ms,transaction_sum_ms,full_replay_ms\n";
 std::vector<double> full_times,execution_sums,transaction_sums;
 for(unsigned rep=0;rep<reps+warm;++rep){bool iswarm=rep<warm;auto fullbegin=Clock::now();double exsum=0,txsum=0;
  for(auto& chunk:cache.chunks){auto begin=Clock::now();const auto& s=chunk.spec;const auto& in=chunk.input;const auto& gold=chunk.expected;auto loaded=Clock::now();
   for(unsigned lane=0;lane<2;++lane){if(split=="block")fill_shard_block(in,lane,lanes[lane]->input);else fill_shard(in,lane,lanes[lane]->input);}
   auto prepared=Clock::now();
   for(auto& lane:lanes){auto params=pack_parameters(lane->input);lane->in_bo.write(lane->input.words.data(),lane->input.words.size()*8,0);lane->param_bo.write(params.data(),params.size()*8,0);lane->in_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);lane->param_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);std::fill(lane->output.begin(),lane->output.end(),UINT64_MAX);lane->out_bo.write(lane->output.data(),lane->output.size()*8,0);lane->out_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);}
   auto exbegin=Clock::now();try{for(auto& lane:lanes)lane->reducer_run.start();auto frames=in.frames()/2;require(frames>0&&frames<=INT32_MAX,"frame count");graph.run(int(frames));for(auto& lane:lanes)lane->reader_run.start();auto deadline=exbegin+std::chrono::seconds(120);for(auto& lane:lanes)wait_for_run("reader",lane->reader_run,deadline);for(auto& lane:lanes)wait_for_run("reducer",lane->reducer_run,deadline);graph.wait(remaining_time(deadline));}
   catch(...){for(auto& lane:lanes){try{lane->reader_run.abort();}catch(...){}try{lane->reducer_run.abort();}catch(...){}}try{graph.reset();}catch(...){}throw;}
   auto exend=Clock::now();for(auto& lane:lanes){require(lane->reader.read_register(0x10)==0,"reader status");require(lane->reducer.read_register(0x10)==0,"reducer status");}auto status=Clock::now();
   std::fill(out.begin(),out.end(),UINT64_MAX);for(unsigned lane=0;lane<2;++lane){auto& x=lanes[lane];x->out_bo.sync(XCL_BO_SYNC_BO_FROM_DEVICE);x->out_bo.read(x->output.data(),x->output.size()*8,0);merge(in,x->output,lane,out);}auto readback=Clock::now();compare(out,gold,rep);auto end=Clock::now();
   if(rep+1==reps+warm)write_output(dir/"outputs"/(s.id+"_output.bin"),in,out);auto saved=Clock::now();double ex=ms(exbegin,exend),tx=ms(begin,end);exsum+=ex;txsum+=tx;
   csv<<rep<<','<<iswarm<<','<<s.id<<','<<ms(begin,loaded)<<','<<ms(loaded,prepared)<<','<<ms(prepared,exbegin)<<','<<ex<<','<<ms(exend,status)<<','<<ms(status,readback)<<','<<ms(readback,end)<<','<<tx<<','<<ms(end,saved)<<','<<out.size()<<'\n';require(bool(csv),"chunk CSV write");
  }
  double full=ms(fullbegin,Clock::now());whole<<rep<<','<<iswarm<<','<<cache.chunks.size()<<','<<exsum<<','<<txsum<<','<<full<<'\n';require(bool(whole),"iteration CSV write");
  if(!iswarm){full_times.push_back(full);execution_sums.push_back(exsum);transaction_sums.push_back(txsum);}std::cout<<"PASS CACHED_REAL_V32_REPLAY repetition="<<rep<<" warmup="<<iswarm<<" chunks="<<cache.chunks.size()<<" execution_sum_ms="<<exsum<<" full_replay_ms="<<full<<'\n'<<std::flush;
 }
 std::ofstream summary(dir/"summary.json");summary<<std::setprecision(12)<<"{\"status\":\"PASS_FULL_REAL_V32_RAW_MAC_REPLAY\",\"chunks\":"<<cache.chunks.size()<<",\"measured\":"<<reps<<",\"warmups\":"<<warm<<",\"xrt_init_ms\":"<<ms(session_begin,initialized)<<",\"execution_sum_median_ms\":"<<median(execution_sums)<<",\"chunk_transaction_sum_median_ms\":"<<median(transaction_sums)<<",\"full_replay_median_ms\":"<<median(full_times)<<",\"scope\":\"steady-state cached inputs: split, uploads, poison, raw MAC, readback and full integer checks; one-time data admission and buffer setup in setup.json; final iteration retains unchanged output saving; excludes PC transport and full inference\"}\n";require(bool(summary),"summary write");
}
#endif
int main(int argc,char**argv){try{
 if(argc==3&&std::string(argv[1])=="--check-data"){
  CachedDataset cache(argv[2]);InputCase scalar,block;std::vector<uint64_t> merged(cache.chunks.front().expected.size());
  const uint64_t *sp=nullptr,*bp=nullptr;
  for(auto& chunk:cache.chunks){const auto& in=chunk.input;
   for(unsigned lane=0;lane<2;++lane){
    fill_shard(in,lane,scalar);fill_shard_block(in,lane,block);
    require(same_parameters(scalar,block)&&scalar.words==block.words,"scalar/block partition differs");
    if(sp){require(sp==scalar.words.data()&&bp==block.words.data(),"lane buffer reallocated");}
    sp=scalar.words.data();bp=block.words.data();
    std::vector<uint64_t> part(block.output_words());
    for(unsigned t=0;t<in.l;++t)std::copy_n(chunk.expected.begin()+(size_t(t)*in.n+lane*block.n)*3,block.n*3,part.begin()+size_t(t)*block.n*3);
    merge(in,part,lane,merged);
   }
   compare(merged,chunk.expected,0);merged[merged.size()/2]^=1;bool caught=false;
   try{compare(merged,chunk.expected,0);}catch(...){caught=true;}require(caught,"corruption undetected");
   std::cout<<"PASS CACHE_SCALAR_BLOCK_SPLIT_MERGE "<<chunk.spec.id<<" words="<<merged.size()<<'\n';
  }
  bool rejected=false;try{fill_shard_block(cache.chunks[0].input,2,block);}catch(...){rejected=true;}require(rejected,"invalid lane accepted");
  rejected=false;try{fill_shard_block(cache.chunks[0].input,0,cache.chunks[0].input);}catch(...){rejected=true;}require(rejected,"alias accepted");
  std::cout<<"PASS ALL_CACHED_CHUNKS stable_buffers=1 corruption_detected=1 invalid_lane_alias_rejected=1\n";return 0;
 }
#ifndef CKKSMAC_PARSER_ONLY
 require(argc==7,"usage: cached_host XCLBIN FIXTURE NEW_RESULTS REPS WARMUPS scalar|block");tiled(argv[1],argv[2],argv[3],number(argv[4],100),number(argv[5],10),argv[6]);return 0;
#else
 throw std::runtime_error("parser-only executable");
#endif
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
