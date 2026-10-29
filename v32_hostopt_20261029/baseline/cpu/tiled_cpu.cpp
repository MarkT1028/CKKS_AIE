#define CPU_BENCH_NO_MAIN
#include "cpu_bench.cpp"
#include <regex>
struct Chunk{std::string id;unsigned t,j,n,l,k;};
static std::vector<Chunk> chunks(const fs::path& root){
 std::ifstream f(root/"chunks.tsv");require(bool(f),"chunk manifest missing");std::string line;std::getline(f,line);require(line=="id\ttower_start\tcoefficient_start\tN\tL\tK","manifest header");std::vector<Chunk> out;
 while(std::getline(f,line)){Chunk c;std::istringstream s(line);require(bool(s>>c.id>>c.t>>c.j>>c.n>>c.l>>c.k),"manifest row");require(c.id=="chunk_"+std::to_string(out.size())&&std::regex_match(c.id,std::regex("chunk_[0-9]+")),"manifest id");out.push_back(c);}require(!out.empty()&&out.size()<=512,"chunk count");return out;
}
int main(int argc,char**argv){try{
 if(argc==2&&std::string(argv[1])=="--self-test"){selftest();return 0;}
 require(argc==7,"usage: tiled_cpu FIXTURE NEW_RESULTS REPS WARMUPS THREADS save|nosave");fs::path root=argv[1],dir=argv[2];require(!fs::exists(dir),"result exists");auto spec=chunks(root);unsigned reps=count(argv[3],100),warm=count(argv[4],10),threads=count(argv[5],2);require(reps>0&&(threads==1||threads==2),"repetitions/threads");bool save=std::string(argv[6])=="save";require(save||std::string(argv[6])=="nosave","save flag");
 fs::create_directories(dir/"outputs");InputCase in;std::vector<uint64_t> out;ComputePool pool(in,out,threads);
 std::ofstream csv(dir/"chunks.csv"),whole(dir/"iterations.csv");csv<<std::fixed<<std::setprecision(6);whole<<std::fixed<<std::setprecision(6);csv<<"repetition,warmup,chunk,load_poison_ms,compute_ms,validation_ms,verified_call_ms,output_save_ms,verified_words\n";whole<<"repetition,warmup,compute_sum_ms,verified_call_sum_ms,full_replay_ms\n";
 std::vector<double> computes,calls,fulls;
 for(unsigned rep=0;rep<reps+warm;++rep){auto fullbegin=Clock::now();double sum=0,call=0;bool iswarm=rep<warm;
  for(auto& c:spec){auto begin=Clock::now();in=read_input(root/"chunks"/(c.id+"_input.bin"));require(in.n==c.n&&in.l==c.l&&in.k==c.k,"manifest shape mismatch");auto expected=read_expected(root/"chunks"/(c.id+"_expected.bin"),in);out.assign(expected.size(),UINT64_MAX);auto loaded=Clock::now();pool.run();auto computed=Clock::now();compare(out,expected);auto checked=Clock::now();if(save&&rep+1==reps+warm)save_output(dir/"outputs"/(c.id+"_output.bin"),in,out);auto saved=Clock::now();double cm=elapsed(loaded,computed),tx=elapsed(begin,checked);sum+=cm;call+=tx;csv<<rep<<','<<iswarm<<','<<c.id<<','<<elapsed(begin,loaded)<<','<<cm<<','<<elapsed(computed,checked)<<','<<tx<<','<<elapsed(checked,saved)<<','<<out.size()<<'\n';require(bool(csv),"CSV write");}
  double full=elapsed(fullbegin,Clock::now());whole<<rep<<','<<iswarm<<','<<sum<<','<<call<<','<<full<<'\n';require(bool(whole),"CSV write");if(!iswarm){computes.push_back(sum);calls.push_back(call);fulls.push_back(full);}std::cout<<"PASS FULL_CPU_REPLAY repetition="<<rep<<" warmup="<<iswarm<<" compute_sum_ms="<<sum<<" full_replay_ms="<<full<<'\n'<<std::flush;
 }
 std::ofstream f(dir/"summary.json");f<<std::setprecision(12)<<"{\"status\":\"PASS_FULL_RAW_MAC_CPU_REPLAY\",\"threads\":"<<threads<<",\"chunks\":"<<spec.size()<<",\"measured\":"<<reps<<",\"warmups\":"<<warm<<",\"compute_sum_median_ms\":"<<med(computes)<<",\"chunk_verified_call_sum_median_ms\":"<<med(calls)<<",\"full_replay_median_ms\":"<<med(fulls)<<",\"scope\":\"u128 accumulation with modulo after each sum; persistent 1/2 compute threads; includes file parsing in full_replay; not OpenFHE or optimal-CPU claim\"}\n";require(bool(f),"summary write");return 0;
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
