#include "variant_config.hpp"
#define main original_timing_main
#include "timed_base.hpp"
#undef main
#include <algorithm>
#include <cmath>
#include <memory>
#include <numeric>

namespace {
#include "expected_reader.hpp"
using Clock=std::chrono::steady_clock;
double ms(Clock::time_point a,Clock::time_point b){return std::chrono::duration<double,std::milli>(b-a).count();}
double median(std::vector<double> v){std::sort(v.begin(),v.end());require(!v.empty(),"no samples");size_t n=v.size();return n%2?v[n/2]:(v[n/2-1]+v[n/2])/2;}
double p95(std::vector<double> v){std::sort(v.begin(),v.end());return v[size_t(std::ceil(v.size()*.95))-1];}
unsigned number(const std::string& s,unsigned max){require(!s.empty()&&s.find_first_not_of("0123456789")==std::string::npos,"invalid repetition count");auto n=std::stoul(s);require(n<=max,"repetition count too large");return unsigned(n);}
// File records contain 3 uint64s per parameter; the HLS m_axi ABI pads each
// 192-bit parameter to a 32-byte stride. Allocate the actual packed byte count.
size_t parameter_buffer_bytes(const InputCase& in){return pack_parameters(in).size()*sizeof(uint64_t);}
InputCase shard(const InputCase& in,unsigned lane) {
    require(in.n>=128&&lane<2,"invalid split");InputCase out=in;out.n=in.n/2;out.words.clear();out.words.reserve(in.words.size()/2);
    for(unsigned pair=0;pair<in.k;++pair)for(unsigned t=0;t<in.l;++t)
        for(unsigned j=0;j<out.n;++j)for(unsigned c=0;c<4;++c)
            out.words.push_back(in.words[((size_t(pair)*in.l+t)*in.n+lane*out.n+j)*4+c]);
    return out;
}
void merge(const InputCase& in,const std::vector<uint64_t>& part,unsigned lane,std::vector<uint64_t>& result) {
    const unsigned n=in.n/2;require(part.size()==size_t(n)*in.l*3,"partial output count");
    for(unsigned t=0;t<in.l;++t)
        std::copy_n(part.begin()+size_t(t)*n*3,n*3,result.begin()+(size_t(t)*in.n+lane*n)*3);
}
void compare(const std::vector<uint64_t>& out,const std::vector<uint64_t>& expected,unsigned rep) {
    require(out.size()==expected.size(),"validation count mismatch");
    for(size_t i=0;i<out.size();++i)
        if(out[i]!=expected[i])throw std::runtime_error("mismatch at repetition "+std::to_string(rep)+" word "+std::to_string(i));
}
std::vector<uint64_t> sink_reference(const InputCase& in) {
    std::vector<uint64_t> expected(10,0);expected[0]=0x53494e4b44494147ULL;uint64_t beat=0;
    for(unsigned t=0;t<in.l;++t)for(unsigned base=0;base<in.n;base+=64)
        for(unsigned pair=0;pair<in.k;++pair)for(unsigned product=0;product<4;++product)
            for(unsigned r=0;r<4;++r)for(unsigned s=0;s<4;++s)for(unsigned j=0;j<64;j+=4,++beat)
                for(unsigned lane=0;lane<4;++lane) {
                    size_t idx=((size_t(pair)*in.l+t)*in.n+base+j+lane)*4;
                    uint64_t a=(in.words[idx+product/2]>>(15*r))&32767,b=(in.words[idx+2+product%2]>>(15*s))&32767,value=a*b;
                    expected[2+lane]+=value;expected[6+lane]^=value<<(beat&31);
                }
    expected[1]=beat;return expected;
}
void selftest(const InputCase& in,const std::vector<uint64_t>& expected) {
    auto packed=pack_parameters(in);
    require(parameter_buffer_bytes(in)==size_t(in.l)*32,"HLS parameter stride must be 32 bytes");
    for(unsigned t=0;t<in.l;++t)
        require(packed[4*t]==in.parameters[t].q&&packed[4*t+1]==in.parameters[t].mu_lo&&packed[4*t+2]==in.parameters[t].mu_hi&&packed[4*t+3]==0,"HLS parameter fields/padding");
    std::vector<uint64_t> result(expected.size(),UINT64_MAX);
    for(unsigned lane=0;lane<2;++lane) {
        auto sub=shard(in,lane);require(sub.frames()*2==in.frames(),"split frame count");
        for(unsigned pair=0;pair<in.k;++pair)for(unsigned t=0;t<in.l;++t)for(unsigned j=0;j<sub.n;++j)for(unsigned c=0;c<4;++c)
            require(sub.words[((size_t(pair)*in.l+t)*sub.n+j)*4+c]==in.words[((size_t(pair)*in.l+t)*in.n+lane*sub.n+j)*4+c],"input partition mismatch");
        std::vector<uint64_t> part(sub.output_words());
        for(unsigned t=0;t<in.l;++t)std::copy_n(expected.begin()+(size_t(t)*in.n+lane*sub.n)*3,sub.n*3,part.begin()+size_t(t)*sub.n*3);
        merge(in,part,lane,result);
    }
    compare(result,expected,0);result[expected.size()/2]^=1;bool caught=false;
    try{compare(result,expected,0);}catch(...){caught=true;}
    require(caught,"validation corruption not caught");
    std::cout<<"PASS HOST_SPLIT_MERGE_AND_FAULT_TEST words="<<expected.size()<<"\n";
}
#ifndef CKKSMAC_PARSER_ONLY
struct Lane {
    InputCase input;
    xrt::kernel reader,reducer;
    xrt::bo in_bo,out_bo,param_bo;
    xrt::run reader_run,reducer_run;
    std::vector<uint64_t> output;
    Lane(const xrt::device& device,const xrt::uuid& uuid,const InputCase& in,unsigned lane):
      input(in),reader(device,uuid,PERF_SHARED?"ct_reader_dual:{ct_reader_dual_1}":("ct_reader:{ct_reader_"+std::to_string(lane+1)+"}"),xrt::kernel::cu_access_mode::exclusive),
      reducer(device,uuid,"ct_reduce_accum:{ct_reduce_accum_"+std::to_string(lane+1)+"}",xrt::kernel::cu_access_mode::exclusive),
      in_bo(device,in.words.size()*8,reader.group_id(0)),out_bo(device,(PERF_SINK?10:in.output_words())*8,reducer.group_id(1)),
      param_bo(device,parameter_buffer_bytes(in),reducer.group_id(2)),reader_run(reader),reducer_run(reducer),output(PERF_SINK?10:in.output_words()) {
        auto params=pack_parameters(input);in_bo.write(input.words.data(),input.words.size()*8,0);param_bo.write(params.data(),params.size()*8,0);
        in_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);param_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);
        reader_run.set_arg(0,in_bo);const unsigned start=PERF_SHARED?5:3;
        reader_run.set_arg(start,input.n);reader_run.set_arg(start+1,input.l);reader_run.set_arg(start+2,input.k);
        reducer_run.set_arg(1,out_bo);reducer_run.set_arg(2,param_bo);reducer_run.set_arg(3,input.n);reducer_run.set_arg(4,input.l);reducer_run.set_arg(5,input.k);
    }
};
void hardware(const fs::path& xclbin,const InputCase& input,const std::vector<uint64_t>& golden,const fs::path& dir,unsigned repetitions,unsigned warmups,const std::string& mode) {
    require(!fs::exists(dir),"result directory exists");require(mode=="resident"||mode=="transfer","invalid mode");
    validate_boot_xclbin(xclbin);validate_boot_marker();
    fs::create_directories(dir);
    auto session=Clock::now();auto session_epoch=std::chrono::system_clock::now();
    xrt::ini::set("Runtime.enable_flat","false");xrt::ini::set("Runtime.force_program_xclbin","false");
    xrt::ini::set("Runtime.ert_polling","true");xrt::ini::set("Runtime.xgq_polling","true");
    auto device=xrt::device(0);auto uuid=device.load_xclbin(xclbin.string());auto graph=xrt::graph(device,uuid,"ckks_graph");
    auto init_end=Clock::now();std::vector<std::unique_ptr<Lane>> lanes;
    const unsigned lane_count=PERF_SPLIT?2:1;
    for(unsigned lane=0;lane<lane_count;++lane)lanes.emplace_back(new Lane(device,uuid,PERF_SPLIT?shard(input,lane):input,lane));
    std::unique_ptr<xrt::kernel> join;std::unique_ptr<xrt::run> join_run;
    if(PERF_SHARED){join.reset(new xrt::kernel(device,uuid,"ct_partials_join:{ct_partials_join_1}",xrt::kernel::cu_access_mode::exclusive));join_run.reset(new xrt::run(*join));join_run->set_arg(3,input.n);join_run->set_arg(4,input.l);join_run->set_arg(5,input.k);}
    graph.reset();auto ready=Clock::now();
    std::ofstream session_file(dir/"session.txt");
    session_file<<"variant="<<PERF_VARIANT_ID<<"\nN="<<input.n<<"\nL="<<input.l<<"\nK="<<input.k
      <<"\nmode="<<mode<<"\ncores="<<PERF_CORES<<"\nrepetitions="<<repetitions<<"\nwarmups="<<warmups
      <<"\nsession_start_epoch_ns="<<std::chrono::duration_cast<std::chrono::nanoseconds>(session_epoch.time_since_epoch()).count()
      <<"\nsession_start_steady_ns="<<std::chrono::duration_cast<std::chrono::nanoseconds>(session.time_since_epoch()).count()
      <<"\ninit_ms="<<ms(session,init_end)<<"\nprepare_ms="<<ms(init_end,ready)<<'\n';
    session_file.close();require(bool(session_file),"session metadata write failed");
    auto expected=PERF_SINK?sink_reference(input):golden;std::vector<uint64_t> output(expected.size());
    std::vector<double> executions,transactions,validations;
    std::ofstream observations(dir/"wait_observations.csv");observations<<std::fixed<<std::setprecision(6);
    observations<<"repetition,warmup,lane,kind,start_returned_session_ms,completion_observed_session_ms\n";
    require(bool(observations),"cannot create wait observations");
    std::ofstream csv(dir/"iterations.csv");require(bool(csv),"cannot create CSV");csv<<std::fixed<<std::setprecision(6);
    csv<<"variant,K,mode,repetition,warmup,upload_ms,poison_ms,launch_ms,execution_ms,status_ms,readback_ms,merge_ms,validation_ms,transaction_ms,verified_words,execution_start_session_ms,execution_end_session_ms\n";
    for(unsigned rep=0;rep<warmups+repetitions;++rep) {
        auto begin=Clock::now();
        if(mode=="transfer")for(auto& lane:lanes){auto params=pack_parameters(lane->input);lane->in_bo.write(lane->input.words.data(),lane->input.words.size()*8,0);lane->param_bo.write(params.data(),params.size()*8,0);lane->in_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);lane->param_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);}
        auto upload_end=Clock::now();
        for(auto& lane:lanes){std::fill(lane->output.begin(),lane->output.end(),UINT64_MAX);lane->out_bo.write(lane->output.data(),lane->output.size()*8,0);lane->out_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);}
        auto execution_begin=Clock::now(),launch_end=execution_begin,execution_end=execution_begin;
        std::array<Clock::time_point,2> reader_started{},reducer_started{},reader_observed{},reducer_observed{};
        try {
            for(unsigned i=0;i<lanes.size();++i){lanes[i]->reducer_run.start();reducer_started[i]=Clock::now();}
            if(join_run)join_run->start();
            uint64_t frames=input.frames()/(PERF_CORES==2?2:1);require(frames>0&&frames<=INT32_MAX,"graph frame count overflow");
            graph.run(int(frames));for(unsigned i=0;i<lanes.size();++i){lanes[i]->reader_run.start();reader_started[i]=Clock::now();}launch_end=Clock::now();
            auto deadline=execution_begin+std::chrono::milliseconds(120000);
            for(unsigned i=0;i<lanes.size();++i){wait_for_run("reader",lanes[i]->reader_run,deadline);reader_observed[i]=Clock::now();}
            if(join_run)wait_for_run("partials_join",*join_run,deadline);
            for(unsigned i=0;i<lanes.size();++i){wait_for_run("reducer",lanes[i]->reducer_run,deadline);reducer_observed[i]=Clock::now();}
            graph.wait(remaining_time(deadline));execution_end=Clock::now();
        }catch(...){for(auto& lane:lanes){try{lane->reader_run.abort();}catch(...){}try{lane->reducer_run.abort();}catch(...){}}if(join_run){try{join_run->abort();}catch(...){}}try{graph.reset();}catch(...){}throw;}
        for(auto& lane:lanes){require(lane->reader.read_register(0x10)==0,"reader status");require(lane->reducer.read_register(0x10)==0,"reducer status");}
        if(join)require(join->read_register(0x10)==0,"join status");auto status_end=Clock::now();
        for(auto& lane:lanes){lane->out_bo.sync(XCL_BO_SYNC_BO_FROM_DEVICE);lane->out_bo.read(lane->output.data(),lane->output.size()*8,0);}auto readback_end=Clock::now();
        if(PERF_SPLIT)for(unsigned lane=0;lane<2;++lane)merge(input,lanes[lane]->output,lane,output);else output=lanes[0]->output;
        auto merge_end=Clock::now();compare(output,expected,rep);auto end=Clock::now();
        double execution=ms(execution_begin,execution_end),transaction=ms(begin,end),validation=ms(merge_end,end);bool warm=rep<warmups;
        if(!warm){executions.push_back(execution);transactions.push_back(transaction);validations.push_back(validation);}
        csv<<PERF_VARIANT_ID<<','<<input.k<<','<<mode<<','<<rep<<','<<warm<<','<<ms(begin,upload_end)<<','<<ms(upload_end,execution_begin)<<','<<ms(execution_begin,launch_end)<<','<<execution<<','<<ms(execution_end,status_end)<<','<<ms(status_end,readback_end)<<','<<ms(readback_end,merge_end)<<','<<validation<<','<<transaction<<','<<output.size()<<','<<ms(session,execution_begin)<<','<<ms(session,execution_end)<<'\n';
        require(bool(csv),"CSV write failed");
        for(unsigned i=0;i<lanes.size();++i){
            observations<<rep<<','<<warm<<','<<i<<",reader,"<<ms(session,reader_started[i])<<','<<ms(session,reader_observed[i])<<'\n';
            observations<<rep<<','<<warm<<','<<i<<",reducer,"<<ms(session,reducer_started[i])<<','<<ms(session,reducer_observed[i])<<'\n';
        }require(bool(observations),"wait observations write failed");
        if(warm||(rep-warmups+1)%10==0||rep+1==warmups+repetitions)std::cout<<"PASS variant="<<PERF_VARIANT_ID<<" repetition="<<rep<<" warmup="<<warm<<" execution_ms="<<execution<<" transaction_ms="<<transaction<<" verified_words="<<output.size()<<"\n"<<std::flush;
    }
    csv.close();require(bool(csv),"CSV close failed");observations.close();require(bool(observations),"observations close failed");
    std::ofstream summary(dir/"summary.csv");summary<<std::fixed<<std::setprecision(6);
    summary<<"variant,K,cores,topology,format,scope,mode,repetitions,warmups,init_ms,prepare_ms,execution_median_ms,execution_p95_ms,execution_min_ms,execution_max_ms,transaction_median_ms,validation_median_ms\n";
    summary<<PERF_VARIANT_ID<<','<<input.k<<','<<PERF_CORES<<','<<(PERF_SHARED?"shared":PERF_SPLIT?"split":"single")<<','<<(PERF_COMPACT?"diagonal":"raw")<<','<<(PERF_SINK?"diagnostic_sink_not_ckks_mac":"raw_ckks_mac")<<','<<mode<<','<<repetitions<<','<<warmups<<','<<ms(session,init_end)<<','<<ms(init_end,ready)<<','<<median(executions)<<','<<p95(executions)<<','<<*std::min_element(executions.begin(),executions.end())<<','<<*std::max_element(executions.begin(),executions.end())<<','<<median(transactions)<<','<<median(validations)<<'\n';summary.close();require(bool(summary),"summary write failed");
    if(PERF_SINK){std::ofstream f(dir/"sink_fingerprint.csv");f<<"index,value\n";for(size_t i=0;i<output.size();++i)f<<i<<','<<output[i]<<'\n';}
    else write_output(dir/"output_last.bin",input,output);
    std::cout<<"PASS "<<(PERF_SINK?"DIAGNOSTIC_SINK_ONLY":"FULL_MAC")<<" execution_median_ms="<<median(executions)<<" transaction_median_ms="<<median(transactions)<<"\n";
}
#endif
}
int main(int argc,char** argv){
try {
    std::cout<<std::fixed<<std::setprecision(6);
    if(argc==4&&std::string(argv[1])=="--check-data") {auto in=read_input(argv[2]);auto expected=read_expected(argv[3],in);selftest(in,expected);return 0;}
    if(argc==5&&std::string(argv[1])=="--preflight") {validate_boot_xclbin(argv[2]);auto in=read_input(argv[3]);read_expected(argv[4],in);print_inspection(in);std::cout<<"PASS PREFLIGHT variant="<<PERF_VARIANT_ID<<"\n";return 0;}
#ifndef CKKSMAC_PARSER_ONLY
    require(argc==9,"usage: perf_host XCLBIN INPUT EXPECTED NEW_RESULTS REPS WARMUPS resident|transfer run");
    require(std::string(argv[8])=="run","last argument must be run");auto in=read_input(argv[2]);auto expected=read_expected(argv[3],in);
    unsigned reps=number(argv[5],10000),warm=number(argv[6],100);require(reps>0,"need measured repetitions");
    hardware(argv[1],in,expected,argv[4],reps,warm,argv[7]);return 0;
#else
    throw std::runtime_error("parser-only executable; no board execution supported");
#endif
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}
}
