#ifndef GA3_IO_PROFILE
#define GA3_IO_PROFILE 0
#endif
#include "../common/sealed_sha256.hpp"
#ifndef GA3_OPT_PROFILE
#define GA3_OPT_PROFILE 2
#endif
static constexpr const char* hostopt_profile=GA3_IO_PROFILE==0?"legacy":GA3_IO_PROFILE==1?"sequential":"sha256";
static_assert(GA3_OPT_PROFILE==2,"All I/O profiles retain the measured cacheable BO path");
#if defined(WINDOW_SOFTWARE_MODEL)
#define CKKSMAC_PARSER_ONLY
#endif
#define FULL_HS4_BACKEND_ONLY
#define GA3_SUPPRESS_LEGACY_MAIN
#if defined(WINDOW_NATIVE_PL) && !defined(CKKSMAC_PARSER_ONLY)
#include "../variants/v32_native_pl_2_pipe/host/bo_host.cpp"
#else
#include "../variants/v32_core_2_pipe/host/bo_host.cpp"
#endif
#undef FULL_HS4_BACKEND_ONLY
#if GA3_IO_PROFILE==0
#include "../legacy_source/common/ga3_source.hpp"
#else
#include "../common/ga3_source.hpp"
#endif
#include "../common/stream_output.hpp"
#include <cstdlib>
#include <sys/resource.h>
namespace {namespace windowed {struct Task {unsigned group,chunk;};}}
#if GA3_OPT_PROFILE==0
#include "../baseline_source/host/ga3_xrt.hpp"
#else
#include "ga3_xrt.hpp"
#endif

namespace {
// Same bounded uint128 arithmetic as the historical ARM reference. Persistent
// worker computes half the coefficients while the controller computes half.
void cpu_range(const InputCase& in,const std::vector<uint64_t>& words,std::vector<uint64_t>& out,unsigned begin,unsigned end){
 for(unsigned t=0;t<in.l;++t){auto q=in.parameters[t].q;for(unsigned j=begin;j<end;++j){U128 a=0,b=0,c=0;
  for(unsigned k=0;k<in.k;++k){size_t i=((size_t(k)*in.l+t)*in.n+j)*4;a+=U128(words[i])*words[i+2];b+=U128(words[i])*words[i+3]+U128(words[i+1])*words[i+2];c+=U128(words[i+1])*words[i+3];}
  size_t i=(size_t(t)*in.n+j)*3;out[i]=a%q;out[i+1]=b%q;out[i+2]=c%q;}}
}
double cpu_window(windowio::Dataset& s,boexp::Worker& worker,bool ascending){
 std::vector<uint64_t> input(s.input_words()),output(s.shape.output_words());auto begin=Clock::now();s.begin_request();
 try{for(unsigned i=0;i<4;++i){unsigned g=ascending?i:3-i;s.pack_cached(g,0,0,1,input.data(),input.size(),i==0);std::fill(output.begin(),output.end(),UINT64_MAX);
  worker.submit([&]{cpu_range(s.shape,input,output,0,s.shape.n/2);});cpu_range(s.shape,input,output,s.shape.n/2,s.shape.n);worker.wait();s.verify(g,0,output);s.retire_job(g,0,false);
 }s.end_request();}catch(...){worker.close();s.cancel_request();throw;}
 return ms(begin,Clock::now());
}
#ifdef WINDOW_SOFTWARE_MODEL
class Model {
 windowio::Dataset& source;std::vector<windowed::Task> jobs;std::array<std::array<std::vector<uint64_t>,2>,2> inputs,outputs;std::vector<uint64_t> merged;fs::path dir;bool active=false;std::array<bool,2> baby_valid{};
public:
 static constexpr const char* execution_backend="SOFTWARE_MODEL_NOT_HARDWARE";static constexpr unsigned aie_tiles=0;
 explicit Model(windowio::Dataset&s):source(s){}
 void configure(const std::vector<windowed::Task>& t,const fs::path& d,bool){require(!active,"model active");jobs=t;dir=d;baby_valid.fill(false);}
 void prepare(unsigned i,unsigned b,boexp::Frame&,Clock::time_point){for(unsigned l=0;l<2;++l){inputs[b][l].resize(source.input_words()/2);
#if GA3_OPT_PROFILE==0
source.pack_cached(jobs.at(i).group,0,l,2,inputs[b][l].data(),inputs[b][l].size(),true);
#else
source.pack_optimized(jobs.at(i).group,l,inputs[b][l].data(),inputs[b][l].size(),GA3_OPT_PROFILE==1,!baby_valid[b]);
#endif
}baby_valid[b]=true;}
 void start(unsigned,unsigned b){require(!active,"model overlapping hardware launches");active=true;InputCase part=source.shape;part.n/=2;for(unsigned l=0;l<2;++l){outputs[b][l].resize(part.output_words());cpu_range(part,inputs[b][l],outputs[b][l],0,part.n);}}
 void wait(unsigned,unsigned){require(active,"model wait without start");}
 void complete(unsigned,unsigned,boexp::Frame&,Clock::time_point){require(active,"model complete");active=false;}
 void finish(unsigned i,unsigned b,boexp::Frame&,Clock::time_point){merged.resize(source.shape.output_words());std::fill(merged.begin(),merged.end(),UINT64_MAX);
#if GA3_OPT_PROFILE==0
for(unsigned l=0;l<2;++l)boexp::merge_from(source.shape,l,outputs[b][l].data(),outputs[b][l].size(),merged);source.verify(jobs[i].group,0,merged);
#else
for(unsigned l=0;l<2;++l)source.merge_verify_lane(jobs[i].group,l,outputs[b][l].data(),outputs[b][l].size(),merged);
#endif
source.retire_job(jobs[i].group,0,false);}
 void save(unsigned i,unsigned){auto path=dir/("group_"+std::to_string(jobs[i].group))/"chunk_0_output.bin";
#if GA3_IO_PROFILE==2
streamio::save_verified_digest(path,source.verified_digest(jobs[i].group));if(source.actual_sample)streamio::save_output_bulk(path,source.shape,merged);
#else
streamio::audit_output(path,source.shape,merged,source.actual_sample);
#endif
 }
 void cancel()noexcept{active=false;}
};
#endif
}
int main(int argc,char**argv){try{
 if(argc==2&&std::string(argv[1])=="--crypto-check"){
  sealedsha::Engine engine;std::cout<<"PASS_USERSPACE_OPENSSL_SHA256 "<<engine.description()<<'\n';return 0;
 }
#ifdef WINDOW_SOFTWARE_MODEL
 if(argc==4&&std::string(argv[1])=="--check-record"){windowio::Record r(argv[2],number(argv[3],4));r.canonical();auto v=r.read_canonical();for(size_t i=0;i<v.size();++i)require(v[i]==r.word(i),"bulk/mmap record differs");std::cout<<"PASS_BULK_CANONICAL_RECORD_EQUIVALENCE words="<<v.size()<<'\n';return 0;}
#endif
 if(argc==3&&std::string(argv[1])=="--validate"){windowio::Dataset source(argv[2]);std::cout<<"PASS_GA3_METADATA full_L="<<source.full_l<<" windows="<<source.blocks.size()*16<<" checked_words_expected="<<source.full_words<<'\n';return 0;}
 require(argc==9,"usage: ga3_host XCLBIN DATA NEW_RESULT smoke|probe|pilot|windows|stream|export REPS WARMUPS ascending|descending MAX_WINDOWS(0=all)");
 fs::path xb=argv[1],data=argv[2],result=argv[3];std::string mode=argv[4],order=argv[7];unsigned reps=number(argv[5],10),warm=number(argv[6],3),limit=number(argv[8],1024);
 require((mode=="smoke"||mode=="probe"||mode=="pilot"||mode=="windows"||mode=="stream"||mode=="export")&&reps>0&&(order=="ascending"||order=="descending")&&!fs::exists(result),"ga3 CLI");
 require((mode=="smoke")==(limit>0),"only smoke may limit full coverage");require((mode=="windows"||mode=="probe"||mode=="smoke")||(reps==1&&warm==0),"stream/export exactly one full replay");
 require(mode!="smoke"||limit==2,"smoke must cover both first and last RNS/coefficient windows");
 const bool asc=order=="ascending",save=mode=="export";auto setup_start=Clock::now();windowio::Dataset source(data);
#ifdef WINDOW_SOFTWARE_MODEL
 Model backend(source);
#elif !defined(CKKSMAC_PARSER_ONLY)
 validate_boot_xclbin(xb);validate_boot_marker();xrt::ini::set("Runtime.enable_flat","false");xrt::ini::set("Runtime.force_program_xclbin","false");xrt::ini::set("Runtime.ert_polling","true");xrt::ini::set("Runtime.xgq_polling","true");auto device=xrt::device(0);auto uuid=device.load_xclbin(xb.string());
#ifdef WINDOW_PURE_PL
 windowed::XrtWindowBackend backend(device,uuid,source,nullptr);
#else
 auto graph=xrt::graph(device,uuid,"ckks_graph");graph.reset();windowed::XrtWindowBackend backend(device,uuid,source,&graph);
#endif
#else
 throw std::runtime_error("parser cannot execute hardware");
#endif
#if defined(WINDOW_SOFTWARE_MODEL) || !defined(CKKSMAC_PARSER_ONLY)
 boexp::Worker worker,cpu_worker;double setup=ms(setup_start,Clock::now());fs::create_directories(result);
 std::ofstream admission_csv(result/"admission.csv");admission_csv<<"window,tower_start,coefficient_start,output_ct,L,admission_ms\n";admission_csv<<std::setprecision(12);
 std::ofstream samples(result/"samples.csv"),traces(result/"traces.csv");samples<<"window,tower_start,coefficient_start,output_ct,L,phase,repetition,warmup,wall_ms,verified_words\n";traces<<"window,repetition,warmup,job,bank,stage,lane,begin_ms,end_ms\n";samples<<std::setprecision(12);traces<<std::setprecision(12);
 std::vector<windowed::Task> tasks;for(unsigned i=0;i<4;++i)tasks.push_back({asc?i:3-i,0});double sums[3]={},admission=0;uint64_t words=0;unsigned window=0;bool hardware_entered=false;
 auto request_start=Clock::now();
 for(const auto& block:source.blocks)for(unsigned ct=0;ct<16;++ct){if(mode=="smoke"&&!((block.tower==0&&block.coefficient==0&&ct==0)||(block.tower==source.blocks.back().tower&&block.coefficient==source.blocks.back().coefficient&&ct==15)))continue;if((mode=="probe"||mode=="pilot")&&!((block.coefficient==0||block.coefficient==122880)&&(ct==0||ct==15)))continue;auto begin=Clock::now();source.admit(block,ct);const double admission_wall=ms(begin,Clock::now());admission+=admission_wall;
  admission_csv<<window<<','<<block.tower<<','<<block.coefficient<<','<<ct<<','<<block.l<<','<<admission_wall<<'\n';
  admission_csv.flush();require(bool(admission_csv),"admission timing write");
  fs::path dest=result/"outputs"/("r"+std::to_string(block.tower)+"_c"+std::to_string(block.coefficient)+"_o"+std::to_string(ct));
  const auto* export_all=std::getenv("V32_GA3_EXPORT_ALL");source.actual_sample=(block.tower==0&&block.coefficient==0&&ct==0)||(block.tower==source.blocks.back().tower&&block.coefficient==source.blocks.back().coefficient&&ct==15)||(export_all&&std::string(export_all)=="1");
  if(save)for(unsigned g=0;g<4;++g)fs::create_directories(dest/("group_"+std::to_string(g)));
  backend.configure(tasks,dest,false);
  for(unsigned phase=0;phase<3;++phase){if(mode!="windows"&&mode!="probe"&&mode!="smoke"&&phase!=1)continue;std::vector<double> times;
   for(unsigned rep=0;rep<warm+reps;++rep){double wall;
    if(phase==1){
#ifndef WINDOW_SOFTWARE_MODEL
     if(!hardware_entered){std::ofstream marker(result/"HARDWARE_ENTERED");marker<<"A run may have started; failed/interrupted execution requires reboot before reuse.\n";marker.close();require(bool(marker),"hardware entry marker write");hardware_entered=true;}
#endif
     source.begin_request();try{auto r=boexp::run_finish_overlap(backend,4,worker,save);wall=r.wall_ms;source.end_request();for(unsigned j=0;j<r.frames.size();++j){auto&f=r.frames[j];for(unsigned k=0;k<f.count;++k){auto&s=f.spans[k];traces<<window<<','<<rep<<','<<(rep<warm)<<','<<j<<','<<f.bank<<','<<s.name<<','<<s.lane<<','<<s.begin<<','<<s.end<<'\n';}}}catch(...){source.cancel_request();throw;}}
    else wall=cpu_window(source,cpu_worker,asc);
    samples<<window<<','<<block.tower<<','<<block.coefficient<<','<<ct<<','<<block.l<<','<<(phase==0?"cpu_before":phase==1?"hardware":"cpu_after")<<','<<rep<<','<<(rep<warm)<<','<<wall<<','<<source.shape.output_words()*4<<'\n';if(rep>=warm)times.push_back(wall);
   }sums[phase]+=median(times);
  }words+=source.shape.output_words()*4;++window;
  samples.flush();traces.flush();require(bool(samples)&&bool(traces),"ga3 result write");
  std::cout<<"PASS_GA3_WINDOW window="<<window<<"/"<<source.blocks.size()*16<<" L="<<block.l<<" checked_words="<<words<<std::endl;
 }
 const double full_wall=ms(request_start,Clock::now());
 std::ofstream policy(result/"hostopt.json");policy<<"{\"profile\":\""<<hostopt_profile<<"\",\"actual_board_performance\":\"PENDING_INDEPENDENT_REVIEW\",\"canonical_output_materialized\":true,\"full_integer_verification\":"<<(GA3_IO_PROFILE==2?"false":"true")<<",\"full_canonical_sha256_verification\":"<<(GA3_IO_PROFILE==2?"true":"false")<<",\"cacheable_BO\":true,\"CPU_arithmetic_unchanged\":true,\"same_CPU_hardware_verification\":true,\"firmware_changed\":false}\n";
 require(bool(policy),"hostopt policy write");
#if GA3_IO_PROFILE!=0
 const auto& a=source.admission_stats();std::ofstream ad(result/"admission_profile.json");ad<<std::setprecision(12)<<"{\"records\":"<<a.records<<",\"bytes\":"<<a.bytes<<",\"header_ms\":"<<a.header_ms<<",\"allocate_ms\":"<<a.allocate_ms<<",\"pread_ms\":"<<a.pread_ms<<",\"range_ms\":"<<a.range_ms<<",\"identity_ms\":"<<a.identity_ms<<",\"retire_ms\":"<<a.retire_ms<<",\"pread_calls\":"<<a.pread_calls<<",\"gold_read_bytes_avoided\":"<<source.avoided_gold_bytes()<<",\"hashed_outputs\":"<<source.digest_count()<<",\"hashed_bytes\":"<<source.digest_bytes()<<",\"sha256_backend\":\""<<source.digest_backend()<<"\",\"retirement_advice\":\"POSIX_FADV_DONTNEED\",\"global_cache_clear\":false}\n";require(bool(ad),"admission substage write");
#endif
worker.close();cpu_worker.close();struct rusage usage{};require(::getrusage(RUSAGE_SELF,&usage)==0,"process resource metrics");std::ofstream resources(result/"resources.json");resources<<"{\"max_RSS_KiB\":"<<usage.ru_maxrss<<",\"minor_faults\":"<<usage.ru_minflt<<",\"major_faults\":"<<usage.ru_majflt<<",\"block_inputs\":"<<usage.ru_inblock<<",\"block_outputs\":"<<usage.ru_oublock<<"}\n";resources.close();require(bool(resources),"resource write");
 require((mode=="probe"||mode=="pilot")?window==16:limit?window==limit:words==source.full_words,"ga3 full RNS/coefficient coverage");
 std::ofstream summary(result/"summary.json");summary<<std::setprecision(12)<<"{\"status\":\"PASS_GA3_RAW_MAC_REPLAY_PENDING_GROUND_RETURN\",\"mode\":\""<<mode<<"\",\"backend\":\""<<decltype(backend)::execution_backend<<"\",\"AIE_compute_tiles\":"<<decltype(backend)::aie_tiles<<",\"L\":"<<source.full_l<<",\"coefficient_windows\":"<<source.coefficient_windows<<",\"windows\":"<<window<<",\"verified_words\":"<<words<<",\"complete_layer_raw_MAC_coverage\":"<<(!limit&&mode!="probe"&&mode!="pilot"&&source.coefficient_windows==16?"true":"false")<<",\"setup_ms\":"<<setup<<",\"admission_ms\":"<<admission<<",\"campaign_wall_ms\":"<<full_wall<<",\"resident_window_median_sum_cpu_before_ms\":"<<sums[0]<<",\"resident_window_median_sum_hardware_ms\":"<<sums[1]<<",\"resident_window_median_sum_cpu_after_ms\":"<<sums[2]<<",\"repetitions_per_window\":"<<reps<<",\"warmups_per_window\":"<<warm<<",\"export\":"<<(save?"true":"false")<<",\"scope\":\"Window sums are NOT whole-layer wall latency. coefficient_windows=2 means first/last coefficient chunks ONLY; 16 means all coefficients. All output cts, groups and RNS towers are covered in the declared scope. windows campaign includes CPU anchors, repeated trials and admission. stream/export wall includes admission, full verification and separate SHA256 audit/sample saving when export. Rotation, im2col, relinearization, activation and live v32 transport remain ground-side.\"}\n";summary.close();require(bool(summary),"ga3 summary write");return 0;
#endif
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
