// Raw CKKS MAC reference: the historical U128 accumulation + one modulus per sum.
// 1 or 2 persistent compute threads. Not an OpenFHE or an optimal-CPU claim.
#include "parser/variant_config.hpp"
#define CKKSMAC_PARSER_ONLY
#define main legacy_parser_main
#include "parser/timed_base.hpp"
#undef main
#include <algorithm>
#include <cmath>
#include <condition_variable>
#include <mutex>
#include <random>
#include <thread>

namespace {
#include "parser/expected_reader.hpp"
using Clock=std::chrono::steady_clock;
double elapsed(Clock::time_point a,Clock::time_point b){return std::chrono::duration<double,std::milli>(b-a).count();}
double med(std::vector<double> a){std::sort(a.begin(),a.end());require(!a.empty(),"no measured samples");auto n=a.size();return n%2?a[n/2]:(a[n/2-1]+a[n/2])/2;}
double p95(std::vector<double> a){std::sort(a.begin(),a.end());return a[size_t(std::ceil(a.size()*.95))-1];}
unsigned count(const char* s,unsigned maximum){std::string t(s);require(!t.empty()&&t.find_first_not_of("0123456789")==std::string::npos,"invalid count");auto n=std::stoul(t);require(n<=maximum,"count exceeds limit");return unsigned(n);}
void compare(const std::vector<uint64_t>& out,const std::vector<uint64_t>& expected){
 require(out.size()==expected.size(),"output size mismatch");
 for(size_t i=0;i<out.size();++i)if(out[i]!=expected[i])throw std::runtime_error("CPU mismatch at word "+std::to_string(i));
}
void save_output(const fs::path& path,const InputCase& in,const std::vector<uint64_t>& out){
 require(!fs::exists(path),"output file exists");require(out.size()==in.output_words(),"saved output length mismatch");
 std::ofstream f(path,std::ios::binary);require(bool(f),"cannot create CPU output");f.write("CKKSMAC1",8);
 auto put=[&](uint64_t value,unsigned bytes){for(unsigned j=0;j<bytes;++j)f.put(char((value>>(8*j))&255));};
 for(uint32_t v:std::array<uint32_t,10>{1,2,in.n,in.l,in.k,3,1,64,0,0})put(v,4);
 put(out.size(),8);put(0,8);for(const auto& p:in.parameters){put(p.q,8);put(p.mu_lo,8);put(p.mu_hi,8);}
 for(auto value:out){put(value,8);}
 f.close();require(bool(f),"CPU output write failed");
}
void compute_range(const InputCase& in,std::vector<uint64_t>& out,unsigned begin,unsigned end){
 for(unsigned t=0;t<in.l;++t){const uint64_t q=in.parameters[t].q;
  for(unsigned j=begin;j<end;++j){U128 s0=0,s1=0,s2=0;
   for(unsigned pair=0;pair<in.k;++pair){const size_t b=((size_t(pair)*in.l+t)*in.n+j)*4;
    const auto a0=in.words[b],a1=in.words[b+1],b0=in.words[b+2],b1=in.words[b+3];
    s0+=U128(a0)*b0;s1+=U128(a0)*b1+U128(a1)*b0;s2+=U128(a1)*b1;
   }
   // q < 2^60 and K <= 16: even s1 < 2^125, so U128 does not overflow.
   size_t b=(size_t(t)*in.n+j)*3;out[b]=uint64_t(s0%q);out[b+1]=uint64_t(s1%q);out[b+2]=uint64_t(s2%q);
  }
 }
}
class ComputePool {
 const InputCase& in;std::vector<uint64_t>& out;unsigned threads;
 std::mutex mutex;std::condition_variable ready,finished;
 std::vector<std::thread> workers;unsigned generation=0,done=0;bool stop=false;
 void worker(unsigned lane){unsigned observed=0;
  for(;;){std::unique_lock<std::mutex> lock(mutex);ready.wait(lock,[&]{return stop||generation!=observed;});
   if(stop){return;}
   observed=generation;lock.unlock();
   compute_range(in,out,in.n*lane/threads,in.n*(lane+1)/threads);
   lock.lock();++done;if(done==threads)finished.notify_one();
  }
 }
public:
 ComputePool(const InputCase& input,std::vector<uint64_t>& output,unsigned n):in(input),out(output),threads(n){
  require(n==1||n==2,"compute thread count must be 1 or 2");
  if(n==2){try{for(unsigned lane=0;lane<n;++lane)workers.emplace_back([this,lane]{worker(lane);});}
   catch(...){ {std::lock_guard<std::mutex> lock(mutex);stop=true;}ready.notify_all();for(auto& w:workers)w.join();throw;}}
 }
 void run(){if(threads==1){compute_range(in,out,0,in.n);return;}
  std::unique_lock<std::mutex> lock(mutex);done=0;++generation;ready.notify_all();finished.wait(lock,[&]{return done==threads;});
 }
 ~ComputePool(){ {std::lock_guard<std::mutex> lock(mutex);stop=true;}ready.notify_all();for(auto& w:workers)w.join();}
};
std::vector<uint64_t> independent_reference(const InputCase& in){
 std::vector<uint64_t> out(in.output_words());
 for(unsigned t=0;t<in.l;++t)for(unsigned j=0;j<in.n;++j)for(unsigned pair=0;pair<in.k;++pair){
  auto q=in.parameters[t].q;size_t b=((size_t(pair)*in.l+t)*in.n+j)*4,o=(size_t(t)*in.n+j)*3;
  const auto a0=in.words[b],a1=in.words[b+1],b0=in.words[b+2],b1=in.words[b+3];
  out[o]=uint64_t((U128(out[o])+U128(a0)*b0%q)%q);
  out[o+1]=uint64_t((U128(out[o+1])+U128(a0)*b1%q+U128(a1)*b0%q)%q);
  out[o+2]=uint64_t((U128(out[o+2])+U128(a1)*b1%q)%q);
 }
 return out;
}
void selftest(){
 std::mt19937_64 rng(20261023);unsigned tests=0;
 for(unsigned k:{1u,3u,16u})for(unsigned pattern=0;pattern<3;++pattern){
  InputCase in;in.n=128;in.l=3;in.k=k;
  for(uint64_t q:{(uint64_t(1)<<48)+1,(uint64_t(1)<<59)-1,(uint64_t(1)<<60)-1}){Parameter p;p.q=q;in.parameters.push_back(p);}
  in.words.resize(size_t(in.n)*in.l*in.k*4);
  for(unsigned pair=0;pair<k;++pair)for(unsigned t=0;t<in.l;++t)for(unsigned j=0;j<in.n;++j)for(unsigned c=0;c<4;++c){
   auto q=in.parameters[t].q;in.words[((size_t(pair)*in.l+t)*in.n+j)*4+c]=pattern==0?0:pattern==1?q-1:rng()%q;
  }
  auto expected=independent_reference(in);
  for(unsigned n:{1u,2u}){std::vector<uint64_t> output(expected.size(),UINT64_MAX);ComputePool pool(in,output,n);
   for(unsigned rep=0;rep<5;++rep){std::fill(output.begin(),output.end(),UINT64_MAX);pool.run();compare(output,expected);}++tests;
  }
 }
 std::vector<uint64_t> a{1,2,3},b=a;b[1]^=1;bool caught=false;try{compare(a,b);}catch(...){caught=true;}require(caught,"fault injection was not detected");
 std::cout<<"PASS CPU_SELFTEST configurations="<<tests<<" repetitions_each=5 edge_zero_max_random=1 corruption_detected=1\n";
}
}
int main(int argc,char** argv){try{
 std::cout<<std::fixed<<std::setprecision(6);
 if(argc==2&&std::string(argv[1])=="--self-test"){selftest();return 0;}
 require(argc==7,"Usage: cpu_bench INPUT EXPECTED NEW_RESULTS REPS WARMUPS THREADS; or --self-test");
 auto in=read_input(argv[1]);auto expected=read_expected(argv[2],in);fs::path dir(argv[3]);
 require(!fs::exists(dir),"result directory already exists");unsigned reps=count(argv[4],10000),warmups=count(argv[5],100),threads=count(argv[6],2);
 require(reps>0&&(threads==1||threads==2),"need repetitions and 1/2 threads");
 std::vector<uint64_t> output(expected.size());auto setup_begin=Clock::now();ComputePool pool(in,output,threads);auto setup_end=Clock::now();
 fs::create_directories(dir);std::ofstream session(dir/"session.txt");
 session<<"scope=raw_ckks_mac\nalgorithm=u128_accumulate_mod_after_sum\nN="<<in.n<<"\nL="<<in.l<<"\nK="<<in.k<<"\ncompute_threads="<<threads
  <<"\nrepetitions="<<reps<<"\nwarmups="<<warmups<<"\nsetup_ms="<<elapsed(setup_begin,setup_end)<<"\nworker_threads_reused="<<(threads==2)<<"\n";
 session.close();require(bool(session),"session write failed");
 std::ofstream csv(dir/"iterations.csv");csv<<std::fixed<<std::setprecision(6);
 csv<<"K,threads,repetition,warmup,poison_ms,compute_ms,validation_ms,verified_call_ms,verified_words\n";
 std::vector<double> computes,calls,validations;
 for(unsigned rep=0;rep<warmups+reps;++rep){auto begin=Clock::now();std::fill(output.begin(),output.end(),UINT64_MAX);auto compute_begin=Clock::now();
  pool.run();auto compute_end=Clock::now();compare(output,expected);auto end=Clock::now();bool warm=rep<warmups;
  double compute=elapsed(compute_begin,compute_end),call=elapsed(begin,end),validation=elapsed(compute_end,end);
  if(!warm){computes.push_back(compute);calls.push_back(call);validations.push_back(validation);}
  csv<<in.k<<','<<threads<<','<<rep<<','<<warm<<','<<elapsed(begin,compute_begin)<<','<<compute<<','<<validation<<','<<call<<','<<output.size()<<'\n';require(bool(csv),"CSV write failed");
  if(warm||(rep-warmups+1)%10==0||rep+1==warmups+reps)std::cout<<"PASS CPU K="<<in.k<<" threads="<<threads<<" repetition="<<rep<<" warmup="<<warm<<" compute_ms="<<compute<<" verified_call_ms="<<call<<" verified_words="<<output.size()<<"\n"<<std::flush;
 }
 csv.close();require(bool(csv),"CSV close failed");
 std::ofstream summary(dir/"summary.csv");summary<<std::fixed<<std::setprecision(6);
 summary<<"K,threads,N,L,repetitions,warmups,compute_median_ms,compute_p95_ms,compute_min_ms,compute_max_ms,verified_call_median_ms,validation_median_ms\n";
 summary<<in.k<<','<<threads<<','<<in.n<<','<<in.l<<','<<reps<<','<<warmups<<','<<med(computes)<<','<<p95(computes)<<','<<*std::min_element(computes.begin(),computes.end())<<','<<*std::max_element(computes.begin(),computes.end())<<','<<med(calls)<<','<<med(validations)<<'\n';summary.close();require(bool(summary),"summary write failed");
 save_output(dir/"output_last.bin",in,output);std::cout<<"PASS CPU_FULL_MAC compute_median_ms="<<med(computes)<<" verified_call_median_ms="<<med(calls)<<"\n";
 return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
