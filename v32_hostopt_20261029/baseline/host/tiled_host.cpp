// Reuse the validated XRT ABI, lane sharding, timeouts and boot UUID guards.
#define PERF_HOST_NO_MAIN
#include "perf_host.cpp"
#include <regex>

struct ChunkSpec{std::string id;unsigned t0,j0,n,l,k;};
static std::vector<ChunkSpec> specifications(const fs::path& root){
 std::ifstream f(root/"chunks.tsv");require(bool(f),"missing chunk manifest");std::string line;
 std::getline(f,line);require(line=="id\ttower_start\tcoefficient_start\tN\tL\tK","chunk manifest header");std::vector<ChunkSpec> all;
 while(std::getline(f,line)){ChunkSpec x;std::istringstream s(line);require(bool(s>>x.id>>x.t0>>x.j0>>x.n>>x.l>>x.k),"chunk manifest row");std::string extra;require(!(s>>extra),"extra chunk fields");require(std::regex_match(x.id,std::regex("chunk_[0-9]+")),"unsafe chunk identifier");require(x.id=="chunk_"+std::to_string(all.size()),"noncanonical chunk order");require(x.n>=128&&x.n<=8192&&x.l>=1&&x.l<=16&&x.k>=1&&x.k<=16,"chunk bounds");all.push_back(x);}
 require(!all.empty()&&all.size()<=512,"invalid chunk count");return all;
}
static InputCase chunk_input(const fs::path& root,const ChunkSpec& s){auto in=read_input(root/"chunks"/(s.id+"_input.bin"));require(in.n==s.n&&in.l==s.l&&in.k==s.k,"manifest/input mismatch");return in;}
#ifndef CKKSMAC_PARSER_ONLY
static void tiled(const fs::path& xclbin,const fs::path& root,const fs::path& dir,unsigned reps,unsigned warm){
 require(reps>=1&&reps<=100&&warm<=10,"repetition count");require(!fs::exists(dir),"result directory exists");auto spec=specifications(root);
 validate_boot_xclbin(xclbin);validate_boot_marker();fs::create_directories(dir/"outputs");
 auto session_begin=Clock::now();xrt::ini::set("Runtime.enable_flat","false");xrt::ini::set("Runtime.force_program_xclbin","false");xrt::ini::set("Runtime.ert_polling","true");xrt::ini::set("Runtime.xgq_polling","true");
 auto device=xrt::device(0);auto uuid=device.load_xclbin(xclbin.string());auto graph=xrt::graph(device,uuid,"ckks_graph");graph.reset();auto initialized=Clock::now();
 std::vector<std::unique_ptr<Lane>> lanes;unsigned old_n=0,old_l=0,old_k=0;
 std::ofstream csv(dir/"chunks.csv"),whole(dir/"iterations.csv");csv<<std::fixed<<std::setprecision(6);whole<<std::fixed<<std::setprecision(6);
 csv<<"repetition,warmup,chunk,load_ms,prepare_ms,upload_poison_ms,execution_ms,status_ms,readback_merge_ms,validation_ms,transaction_ms,output_save_ms,verified_words\n";
 whole<<"repetition,warmup,chunks,execution_sum_ms,transaction_sum_ms,full_replay_ms\n";
 std::vector<double> full_times,execution_sums,transaction_sums;
 for(unsigned rep=0;rep<reps+warm;++rep){bool iswarm=rep<warm;auto fullbegin=Clock::now();double exsum=0,txsum=0;
  for(auto& s:spec){auto begin=Clock::now();auto in=chunk_input(root,s);auto gold=read_expected(root/"chunks"/(s.id+"_expected.bin"),in);auto loaded=Clock::now();
   if(in.n!=old_n||in.l!=old_l||in.k!=old_k){lanes.clear();for(unsigned lane=0;lane<2;++lane)lanes.emplace_back(new Lane(device,uuid,shard(in,lane),lane));old_n=in.n;old_l=in.l;old_k=in.k;}
   else for(unsigned lane=0;lane<2;++lane)fill_shard(in,lane,lanes[lane]->input);
   auto prepared=Clock::now();
   for(auto& lane:lanes){auto params=pack_parameters(lane->input);lane->in_bo.write(lane->input.words.data(),lane->input.words.size()*8,0);lane->param_bo.write(params.data(),params.size()*8,0);lane->in_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);lane->param_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);std::fill(lane->output.begin(),lane->output.end(),UINT64_MAX);lane->out_bo.write(lane->output.data(),lane->output.size()*8,0);lane->out_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);}
   auto exbegin=Clock::now();try{for(auto& lane:lanes)lane->reducer_run.start();auto frames=in.frames()/2;require(frames>0&&frames<=INT32_MAX,"frame count");graph.run(int(frames));for(auto& lane:lanes)lane->reader_run.start();auto deadline=exbegin+std::chrono::seconds(120);for(auto& lane:lanes)wait_for_run("reader",lane->reader_run,deadline);for(auto& lane:lanes)wait_for_run("reducer",lane->reducer_run,deadline);graph.wait(remaining_time(deadline));}
   catch(...){for(auto& lane:lanes){try{lane->reader_run.abort();}catch(...){}try{lane->reducer_run.abort();}catch(...){}}try{graph.reset();}catch(...){}throw;}
   auto exend=Clock::now();for(auto& lane:lanes){require(lane->reader.read_register(0x10)==0,"reader status");require(lane->reducer.read_register(0x10)==0,"reducer status");}auto status=Clock::now();
   std::vector<uint64_t> out(in.output_words());for(unsigned lane=0;lane<2;++lane){auto& x=lanes[lane];x->out_bo.sync(XCL_BO_SYNC_BO_FROM_DEVICE);x->out_bo.read(x->output.data(),x->output.size()*8,0);merge(in,x->output,lane,out);}auto readback=Clock::now();compare(out,gold,rep);auto end=Clock::now();
   if(rep+1==reps+warm)write_output(dir/"outputs"/(s.id+"_output.bin"),in,out);auto saved=Clock::now();double ex=ms(exbegin,exend),tx=ms(begin,end);exsum+=ex;txsum+=tx;
   csv<<rep<<','<<iswarm<<','<<s.id<<','<<ms(begin,loaded)<<','<<ms(loaded,prepared)<<','<<ms(prepared,exbegin)<<','<<ex<<','<<ms(exend,status)<<','<<ms(status,readback)<<','<<ms(readback,end)<<','<<tx<<','<<ms(end,saved)<<','<<out.size()<<'\n';require(bool(csv),"chunk CSV write");
  }
  double full=ms(fullbegin,Clock::now());whole<<rep<<','<<iswarm<<','<<spec.size()<<','<<exsum<<','<<txsum<<','<<full<<'\n';require(bool(whole),"iteration CSV write");
  if(!iswarm){full_times.push_back(full);execution_sums.push_back(exsum);transaction_sums.push_back(txsum);}std::cout<<"PASS FULL_REAL_V32_REPLAY repetition="<<rep<<" warmup="<<iswarm<<" chunks="<<spec.size()<<" execution_sum_ms="<<exsum<<" full_replay_ms="<<full<<'\n'<<std::flush;
 }
 std::ofstream summary(dir/"summary.json");summary<<std::setprecision(12)<<"{\"status\":\"PASS_FULL_REAL_V32_RAW_MAC_REPLAY\",\"chunks\":"<<spec.size()<<",\"measured\":"<<reps<<",\"warmups\":"<<warm<<",\"xrt_init_ms\":"<<ms(session_begin,initialized)<<",\"execution_sum_median_ms\":"<<median(execution_sums)<<",\"chunk_transaction_sum_median_ms\":"<<median(transaction_sums)<<",\"full_replay_median_ms\":"<<median(full_times)<<",\"scope\":\"includes on-board file parsing, uploads, raw MAC, readback, integer checking; final repetition includes output saving; excludes PC export/network/import/relinearization\"}\n";require(bool(summary),"summary write");
}
#endif
int main(int argc,char**argv){try{
 if(argc==3&&std::string(argv[1])=="--check-data"){auto root=fs::path(argv[2]);for(auto& s:specifications(root)){auto in=chunk_input(root,s);auto expected=read_expected(root/"chunks"/(s.id+"_expected.bin"),in);selftest(in,expected);}std::cout<<"PASS ALL_CHUNK_HOST_PARSERS_AND_SPLIT_MERGE\n";return 0;}
#ifndef CKKSMAC_PARSER_ONLY
 require(argc==6,"usage: tiled_host XCLBIN FIXTURE NEW_RESULTS REPS WARMUPS");tiled(argv[1],argv[2],argv[3],number(argv[4],100),number(argv[5],10));return 0;
#else
 throw std::runtime_error("parser-only executable");
#endif
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
