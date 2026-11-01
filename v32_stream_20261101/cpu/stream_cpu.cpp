#define CPU_BENCH_NO_MAIN
#include "../reference/cpu/cpu_bench.cpp"
#include "../reference/common/dataset_cache.hpp"
#include "../common/mapped_source.hpp"
#include "../common/io_metrics.hpp"

int main(int argc,char** argv){try{
 if(argc==2&&std::string(argv[1])=="--self-test"){selftest();return 0;}
 require(argc==6,"usage: stream_cpu DATA NEW_RESULTS REPS WARMUPS descending|ascending");fs::path data=argv[1],dir=argv[2];auto reps=count(argv[3],20),warm=count(argv[4],3);std::string order=argv[5];require(reps&&warm<=3&&(order=="descending"||order=="ascending")&&!fs::exists(dir),"stream CPU arguments/results");fs::create_directories(dir);
 auto setup_start=Clock::now();streamio::Dataset source(data);InputCase input;input.n=source.shape.n;input.l=source.shape.l;input.k=source.shape.k;input.parameters=source.shape.parameters;input.words.resize(source.input_words());std::vector<uint64_t> output(input.output_words());ComputePool pool(input,output,2);
 std::ofstream setup(dir/"setup.json");setup<<std::setprecision(12)<<"{\"setup_ms\":"<<elapsed(setup_start,Clock::now())<<",\"threads\":2,\"application_input_heap_bytes\":"<<input.words.size()*8<<",\"application_output_heap_bytes\":"<<output.size()*8<<",\"mmap_is_file_backed_not_heap_copy\":true,\"shared_validation_in_each_request_wall\":true}\n";setup.close();require(bool(setup),"stream CPU setup write");
 std::ofstream whole(dir/"iterations.csv"),groups(dir/"groups.csv"),chunks(dir/"chunks.csv"),resources(dir/"resources.jsonl");for(auto* f:{&whole,&groups,&chunks,&resources})*f<<std::fixed<<std::setprecision(6);
 whole<<"repetition,warmup,export_only,groups,request_wall_ms,shared_validate_ms,group_wall_sum_ms,pack_work_sum_ms,compute_sum_ms,verify_work_sum_ms,verified_words\n";
 groups<<"repetition,warmup,ordinal,group,group_wall_ms,pack_work_ms,compute_ms,verify_work_ms,verified_words\n";chunks<<"repetition,warmup,group,chunk,pack_ms,compute_ms,verify_ms,checked_words\n";std::vector<double> walls,computes;
 for(unsigned rep=0;rep<reps+warm;++rep){const bool w=rep<warm;auto counters=streamio::Metrics::now();auto start=Clock::now();source.begin_request();double shared=elapsed(start,Clock::now()),pack=0,compute=0,verify=0,group_wall=0;uint64_t checked=0;std::ostringstream gr,cr;gr<<std::fixed<<std::setprecision(6);cr<<std::fixed<<std::setprecision(6);
  try{for(unsigned ordinal=0;ordinal<6;++ordinal){unsigned g=order=="ascending"?ordinal:5-ordinal;auto gs=Clock::now();double gp=0,gc=0,gv=0;
   for(unsigned i=0;i<source.dimensions.chunks;++i){auto p=Clock::now();source.pack(g,i,0,1,input.words.data(),input.words.size());auto pe=Clock::now();std::fill(output.begin(),output.end(),UINT64_MAX);auto cs=Clock::now();pool.run();auto ce=Clock::now();source.verify(g,i,output);auto ve=Clock::now();auto dp=elapsed(p,pe),dc=elapsed(cs,ce),dv=elapsed(ce,ve);gp+=dp;gc+=dc;gv+=dv;checked+=output.size();cr<<rep<<','<<w<<','<<g<<','<<i<<','<<dp<<','<<dc<<','<<dv<<','<<output.size()<<'\n';}
   auto gw=elapsed(gs,Clock::now());group_wall+=gw;pack+=gp;compute+=gc;verify+=gv;gr<<rep<<','<<w<<','<<ordinal<<','<<g<<','<<gw<<','<<gp<<','<<gc<<','<<gv<<','<<source.dimensions.chunks*source.shape.output_words()<<'\n';
  }source.end_request();}catch(...){source.cancel_request();throw;}
  auto wall=elapsed(start,Clock::now());auto after=streamio::Metrics::now();require(checked==source.verified_words(),"stream CPU incomplete output");whole<<rep<<','<<w<<",0,6,"<<wall<<','<<shared<<','<<group_wall<<','<<pack<<','<<compute<<','<<verify<<','<<checked<<'\n';groups<<gr.str();chunks<<cr.str();resources<<"{\"repetition\":"<<rep<<",\"warmup\":"<<w<<",\"process_metrics\":"<<after.delta_json(counters)<<"}\n";for(auto* f:{&whole,&groups,&chunks,&resources}){f->flush();require(bool(*f),"stream CPU result write");}
  if(!w){walls.push_back(wall);computes.push_back(compute);}std::cout<<"PASS_STREAM_CPU_SIX_GROUPS repetition="<<rep<<" warmup="<<w<<" request_wall_ms="<<wall<<" compute_sum_ms="<<compute<<" checked_words="<<checked<<'\n'<<std::flush;
 }
 std::ofstream summary(dir/"summary.json");summary<<std::setprecision(12)<<"{\"status\":\"PASS_STREAM_CPU_SIX_GROUPS\",\"measured\":"<<reps<<",\"warmups\":"<<warm<<",\"request_wall_median_ms\":"<<med(walls)<<",\"compute_sum_median_ms\":"<<med(computes)<<",\"protocol\":\"stream_request_v1\",\"scope\":\"Same mapped compact source and per-request shared validation as hardware; historical2-thread raw MAC and full output verification. Request includes pack/read faults; setup separate. Not OpenFHE full-layer or optimal-CPU claim.\"}\n";summary.close();require(bool(summary),"stream CPU summary write");return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
