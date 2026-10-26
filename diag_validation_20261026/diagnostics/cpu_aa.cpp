// Diagnostic A/A blocks. The original arithmetic, parser and ComputePool are
// included byte-for-byte up to the original CLI main; formal hosts are untouched.
#include "cpu_reference.inc"
#include <cstdint>

namespace {
struct AAPhase {const char* id;const char* policy;bool long_warm;};
const std::array<AAPhase,10> aa_phases{{
 {"short_A1","reuse",false},{"short_B","copy",false},{"short_A2","reuse",false},
 {"short_C","reallocate",false},{"short_A3","reuse",false},
 {"long_A1","reuse",true},{"long_B","copy",true},{"long_A2","reuse",true},
 {"long_C","reallocate",true},{"long_A3","reuse",true}
}};
uint64_t address(const std::vector<uint64_t>& v){return uint64_t(reinterpret_cast<std::uintptr_t>(v.data()));}
void aa_run(InputCase& in,const std::vector<uint64_t>& expected,const fs::path& dir,
            unsigned threads,const std::vector<int>& cpus,unsigned reps,unsigned blocks,unsigned short_warm,unsigned long_warm){
 require(!fs::exists(dir),"results directory exists");
 require(reps>0&&blocks>=2&&short_warm<=long_warm,"invalid A/A counts");
 fs::create_directories(dir);
 const auto seed=in.words;std::vector<uint64_t> output(expected.size());
 const auto stable_input=address(in.words),stable_output=address(output);
 ComputePool pool(in,output,threads,true,cpus);
 pool.save_affinity(dir/"affinity_before.json","pinned");
 std::ofstream session(dir/"session.json");
 session<<"{\"scope\":\"diagnostic_cpu_AA_not_formal_CPU_HW_comparison\",\"algorithm\":\"u128_accumulate_mod_after_sum\","
  <<"\"N\":"<<in.n<<",\"L\":"<<in.l<<",\"K\":"<<in.k<<",\"threads\":"<<threads
  <<",\"repetitions_per_block\":"<<reps<<",\"blocks_per_phase\":"<<blocks<<",\"short_warmups_per_block\":"<<short_warm
  <<",\"long_warmups_per_block\":"<<long_warm<<",\"phases\":10,\"same_process_and_thread_pool\":true,"
  <<"\"stable_input_virtual_address\":"<<stable_input<<",\"stable_output_virtual_address\":"<<stable_output
  <<",\"input_copy_seed_buffer_kept_alive\":true,\"physical_page_identity_not_measured\":true}\n";
 session.close();require(bool(session),"session write failed");
 std::ofstream rows(dir/"iterations.csv"),summary(dir/"blocks.csv");rows<<std::fixed<<std::setprecision(6);summary<<std::fixed<<std::setprecision(6);
 rows<<"K,threads,phase,policy,block,repetition,warmup,poison_ms,compute_ms,validation_ms,verified_call_ms,verified_words,input_address,output_address,cpu0_start,cpu0_end,cpu1_start,cpu1_end\n";
 summary<<"phase,policy,block,K,threads,repetitions,warmups,prepare_ms,input_address,output_address,stable_input_address,stable_output_address,compute_median_ms,compute_p95_ms,compute_min_ms,compute_max_ms,verified_call_median_ms\n";
 for(const auto& phase:aa_phases){
  std::vector<uint64_t> held_input,held_output;
  const bool reallocating=std::string(phase.policy)=="reallocate";
  if(reallocating){held_input.swap(in.words);held_output.swap(output);}
  uint64_t previous_input=0,previous_output=0;
  const unsigned warm=phase.long_warm?long_warm:short_warm;
  for(unsigned block=0;block<blocks;++block){
   auto prepare_begin=Clock::now();
   if(reallocating){std::vector<uint64_t> next_input(seed),next_output(expected.size());in.words.swap(next_input);output.swap(next_output);}
   else if(std::string(phase.policy)=="copy")std::copy(seed.begin(),seed.end(),in.words.begin());
   auto prepare_end=Clock::now();
   const auto ia=address(in.words),oa=address(output);
   if(reallocating){require(ia!=stable_input&&oa!=stable_output,"stable buffers unexpectedly reused during reallocation");
    if(block)require(ia!=previous_input&&oa!=previous_output,"adjacent reallocation reused a live buffer");}
   else require(ia==stable_input&&oa==stable_output,"A/A reuse buffer address changed");
   previous_input=ia;previous_output=oa;
   std::vector<double> computes,calls;
   for(unsigned rep=0;rep<warm+reps;++rep){
    auto begin=Clock::now();std::fill(output.begin(),output.end(),UINT64_MAX);auto compute_begin=Clock::now();
    pool.run();auto compute_end=Clock::now();compare(output,expected);auto end=Clock::now();bool is_warm=rep<warm;
    double compute=elapsed(compute_begin,compute_end),call=elapsed(begin,end);
    if(!is_warm){computes.push_back(compute);calls.push_back(call);}
    rows<<in.k<<','<<threads<<','<<phase.id<<','<<phase.policy<<','<<block<<','<<rep<<','<<is_warm<<','<<elapsed(begin,compute_begin)<<','<<compute<<','<<elapsed(compute_end,end)<<','<<call<<','<<output.size()<<','<<ia<<','<<oa<<','<<pool.cpu_begin[0]<<','<<pool.cpu_end[0]<<','<<pool.cpu_begin[1]<<','<<pool.cpu_end[1]<<'\n';require(bool(rows),"iteration CSV write failed");
   }
   summary<<phase.id<<','<<phase.policy<<','<<block<<','<<in.k<<','<<threads<<','<<reps<<','<<warm<<','<<elapsed(prepare_begin,prepare_end)<<','<<ia<<','<<oa<<','<<stable_input<<','<<stable_output<<','<<med(computes)<<','<<p95(computes)<<','<<*std::min_element(computes.begin(),computes.end())<<','<<*std::max_element(computes.begin(),computes.end())<<','<<med(calls)<<'\n';
   rows.flush();summary.flush();require(bool(rows)&&bool(summary),"block CSV write failed");
   std::cout<<"PASS CPU_AA phase="<<phase.id<<" block="<<block<<" compute_median_ms="<<med(computes)<<" verified_words="<<output.size()<<'\n'<<std::flush;
  }
  if(reallocating){in.words.swap(held_input);output.swap(held_output);}
  require(address(in.words)==stable_input&&address(output)==stable_output,"stable buffer restore failed");
 }
 rows.close();summary.close();require(bool(rows)&&bool(summary),"CSV close failed");
 pool.save_affinity(dir/"affinity_after.json","pinned");
 compare(output,expected);save_output(dir/"output_last.bin",in,output);
 std::cout<<"PASS CPU_AA_ALL_PHASES scope=diagnostic_only phases=10 same_process=1 same_pool=1\n";
}
}
int main(int argc,char** argv){try{
 std::cout<<std::fixed<<std::setprecision(6);
 if(argc==2&&std::string(argv[1])=="--self-test"){selftest();return 0;}
 require(argc==11,"usage: cpu_aa INPUT EXPECTED NEW_RESULTS THREADS CPU_LIST REPS BLOCKS SHORT_WARM LONG_WARM run");
 require(std::string(argv[10])=="run","last argument must be run");
 auto in=read_input(argv[1]);auto expected=read_expected(argv[2],in);
 unsigned threads=count(argv[4],2),reps=count(argv[6],1000),blocks=count(argv[7],100),sw=count(argv[8],100),lw=count(argv[9],100);
 require(threads==1||threads==2,"threads must be 1 or 2");
 aa_run(in,expected,argv[3],threads,parse_cpus(argv[5]),reps,blocks,sw,lw);return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
