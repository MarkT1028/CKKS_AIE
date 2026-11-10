#ifdef FINISH_MODEL
#define CKKSMAC_PARSER_ONLY
#endif
#define FULL_HS4_BACKEND_ONLY
#include <variants/v32_native_pl_2_pipe/host/bo_host.cpp>
#undef FULL_HS4_BACKEND_ONLY
#include "../common/sealed_sha256.hpp"
#include "../common/source.hpp"
#include <common/stream_output.hpp>
#include <sys/resource.h>
#ifdef FINISH_MODEL
#include "../tests/mock_xrt.hpp"
#endif
#if !defined(CKKSMAC_PARSER_ONLY) || defined(FINISH_MODEL)
#include "backend.hpp"
#endif

int main(int argc,char**argv){try{
    if(argc==2&&std::string(argv[1])=="--crypto-check"){
        finishsha::Engine engine;std::cout<<"PASS_CANONICAL_SHA256_SELFTEST "<<engine.description()<<'\n';return 0;
    }
    if(argc==3&&std::string(argv[1])=="--validate"){
        finishopt::Source source(argv[2]);std::cout<<"PASS_REAL_GA3_METADATA windows="<<source.blocks.size()*16<<" words="<<source.full_words<<'\n';return 0;
    }
#if !defined(CKKSMAC_PARSER_ONLY) || defined(FINISH_MODEL)
    require(argc==7,"usage: finish_host XCLBIN DATA NEW_RESULTS merge1|direct1|direct2 smoke|pilot|full|export ascending|descending");
    const fs::path xb=argv[1],data=argv[2],result=argv[3];
    const std::string profile=argv[4],mode=argv[5],order=argv[6];
    require((profile=="merge1"||profile=="direct1"||profile=="direct2")&&(mode=="smoke"||mode=="pilot"||mode=="full"||mode=="export")&&(order=="ascending"||order=="descending")&&!fs::exists(result),"invalid profile/mode/order or existing result");
    const bool direct=profile!="merge1",save=mode=="export",ascending=order=="ascending";
    const unsigned batch_limit=profile=="direct2"?2:1;
    const char* all=std::getenv("V32_GA3_EXPORT_ALL");require(!all||std::string(all)=="0"||std::string(all)=="1","export all must be0 or1");
    auto start_setup=Clock::now();finishopt::Source source(data);finishsha::Engine engine;
#ifdef FINISH_MODEL
    xrt::device device;xrt::uuid uuid;
#else
    validate_boot_xclbin(xb);validate_boot_marker();
    xrt::ini::set("Runtime.enable_flat","false");xrt::ini::set("Runtime.force_program_xclbin","false");
    xrt::ini::set("Runtime.ert_polling","true");xrt::ini::set("Runtime.xgq_polling","true");
    auto device=xrt::device(0);auto uuid=device.load_xclbin(xb.string());
#endif
    InputCase maximum;maximum.n=8192;maximum.l=16;maximum.k=16;
    finishopt::Backend backend(device,uuid,maximum,engine);boexp::Worker worker;
    std::array<finishopt::Window,2> slots;
    std::vector<std::pair<finishopt::Block,unsigned>> schedule;
    for(const auto& b:source.blocks)for(unsigned ct=0;ct<16;++ct){
        if(mode=="smoke"&&!((b.tower==0&&b.coefficient==0&&ct==0)||(b.tower==source.blocks.back().tower&&b.coefficient==source.blocks.back().coefficient&&ct==15)))continue;
        if(mode=="pilot"&&!((b.coefficient==0||b.coefficient==122880)&&(ct==0||ct==15)))continue;
        schedule.push_back({b,ct});
    }
    const unsigned expected=mode=="smoke"?2:mode=="pilot"?16:unsigned(source.blocks.size()*16);
    require(schedule.size()==expected,"schedule incomplete");
    fs::create_directories(result);
    std::ofstream admission(result/"admission.csv"),batches(result/"batches.csv"),windows(result/"windows.csv"),traces(result/"traces.csv");
    admission<<"window,batch,slot,tower_start,coefficient_start,output_ct,L,admission_ms\n";
    batches<<"batch,first_window,windows,tower_start,coefficient_start,L,wall_ms,verified_words,copied_bytes,synced_bytes,cache_hits\n";
    windows<<"window,batch,slot,tower_start,coefficient_start,output_ct,L,verified_words,copied_bytes,synced_bytes,cache_hits,digest0,digest1,digest2,digest3\n";
    traces<<"batch,task,window,slot,group,bank,stage,lane,begin_ms,end_ms\n";
    for(auto* f:{&admission,&batches,&windows,&traces}){*f<<std::setprecision(12);require(bool(*f),"result file create failed");}
    const double setup_ms=ms(start_setup,Clock::now());
    auto request_start=Clock::now();double resident_ms=0,admission_ms=0;uint64_t words=0,total_copy=0,total_sync=0,total_hits=0;
    unsigned batch=0,ordinal=0;bool entered=false;
    while(ordinal<schedule.size()){
        const auto block=schedule[ordinal].first;unsigned count=1;
        while(count<batch_limit&&ordinal+count<schedule.size()&&schedule[ordinal+count].first.tower==block.tower&&schedule[ordinal+count].first.coefficient==block.coefficient)++count;
        std::vector<finishopt::Window*> contexts;
        for(unsigned s=0;s<count;++s){
            auto t=Clock::now();source.admit(block,schedule[ordinal+s].second,slots[s]);const double elapsed=ms(t,Clock::now());admission_ms+=elapsed;
            admission<<ordinal+s<<','<<batch<<','<<s<<','<<block.tower<<','<<block.coefficient<<','<<slots[s].ct<<','<<block.l<<','<<elapsed<<'\n';
            contexts.push_back(&slots[s]);
        }
#ifndef FINISH_MODEL
        if(!entered){std::ofstream flag(result/"HARDWARE_ENTERED");flag<<"Failed/interrupted active host requires reboot before another hardware test.\n";flag.close();require(bool(flag),"hardware entry marker failed");entered=true;}
#endif
        const auto batch_start=Clock::now();
        for(auto* w:contexts)w->begin();
        backend.configure(contexts,ascending,direct,result/"outputs",all&&std::string(all)=="1");
        const double configure_ms=ms(batch_start,Clock::now());
        const auto replay=boexp::run_finish_overlap(backend,count*4,worker,save);
        for(auto* w:contexts)w->end();
        const double batch_wall=ms(batch_start,Clock::now());resident_ms+=batch_wall;
        uint64_t batch_words=0,copy=0,sync=0,hits=0;
        for(unsigned s=0;s<count;++s){
            auto& w=slots[s];const auto checked=w.shape.output_words()*4;batch_words+=checked;
            windows<<ordinal+s<<','<<batch<<','<<s<<','<<w.tower<<','<<w.coefficient<<','<<w.ct<<','<<w.shape.l<<','<<checked<<','<<backend.copied_bytes(s)<<','<<backend.synced_bytes(s)<<','<<backend.cache_hits(s);
            for(const auto& digest:w.digests)windows<<','<<digest;windows<<'\n';
            copy+=backend.copied_bytes(s);sync+=backend.synced_bytes(s);hits+=backend.cache_hits(s);
        }
        for(unsigned i=0;i<replay.frames.size();++i){const auto& f=replay.frames[i];const auto task=backend.schedule()[i];
            for(unsigned j=0;j<f.count;++j){const auto& span=f.spans[j];traces<<batch<<','<<i<<','<<ordinal+task.slot<<','<<task.slot<<','<<task.group<<','<<f.bank<<','<<span.name<<','<<span.lane<<','<<configure_ms+span.begin<<','<<configure_ms+span.end<<'\n';}
        }
        batches<<batch<<','<<ordinal<<','<<count<<','<<block.tower<<','<<block.coefficient<<','<<block.l<<','<<batch_wall<<','<<batch_words<<','<<copy<<','<<sync<<','<<hits<<'\n';
        words+=batch_words;total_copy+=copy;total_sync+=sync;total_hits+=hits;ordinal+=count;++batch;
        for(auto* f:{&admission,&batches,&windows,&traces}){f->flush();require(bool(*f),"result write failed");}
        std::cout<<"PASS_FINISH_BATCH batch="<<batch<<" windows="<<ordinal<<'/'<<schedule.size()<<" words="<<words<<std::endl;
    }
    const double request_ms=ms(request_start,Clock::now());worker.close();
    require(ordinal==expected&&(mode=="smoke"||mode=="pilot"||words==source.full_words),"final full coverage differs");
    require(backend.hashed_outputs()==ordinal*4&&total_copy==total_sync,"complete SHA/upload accounting");
    const auto& a=source.stats();std::ofstream ad(result/"admission_profile.json");
    ad<<std::setprecision(12)<<"{\"records\":"<<a.records<<",\"bytes\":"<<a.bytes<<",\"logical_input_bytes\":"<<a.logical_bytes<<",\"packed_records\":"<<a.packed_records<<",\"raw_records\":"<<a.raw_records<<",\"packed_payload_bytes\":"<<a.packed_payload_bytes<<",\"header_ms\":"<<a.header_ms<<",\"allocate_ms\":"<<a.allocate_ms<<",\"pread_ms\":"<<a.pread_ms<<",\"range_ms\":"<<a.range_ms<<",\"decode_ms\":"<<a.decode_ms<<",\"identity_ms\":"<<a.identity_ms<<",\"retire_ms\":"<<a.retire_ms<<",\"pread_calls\":"<<a.pread_calls<<",\"retirement_advice\":\"POSIX_FADV_DONTNEED\",\"global_cache_clear\":false}";
    ad.close();require(bool(ad),"admission profile write failed");
    struct rusage usage{};require(::getrusage(RUSAGE_SELF,&usage)==0,"resource snapshot failed");
    std::ofstream resources(result/"resources.json");resources<<"{\"max_RSS_KiB\":"<<usage.ru_maxrss<<",\"minor_faults\":"<<usage.ru_minflt<<",\"major_faults\":"<<usage.ru_majflt<<",\"block_inputs\":"<<usage.ru_inblock<<",\"block_outputs\":"<<usage.ru_oublock<<"}";resources.close();require(bool(resources),"resources write failed");
    std::ofstream summary(result/"summary.json");summary<<std::setprecision(12);
    summary<<"{\"status\":\"PASS_DECLARED_GA3_MAC_PENDING_INDEPENDENT_REVIEW\",\"protocol\":\"finish_batch_v1\",\"backend\":\""
#ifdef FINISH_MODEL
        <<"SOFTWARE_MODEL_NOT_HARDWARE"
#else
        <<"XRT_PURE_PL"
#endif
        <<"\",\"profile\":\""<<profile<<"\",\"mode\":\""<<mode<<"\",\"order\":\""<<order<<"\",\"full_N\":131072,\"L\":"<<source.full_l<<",\"K\":16,\"coefficient_windows\":"<<source.coefficient_windows<<",\"windows\":"<<ordinal<<",\"batches\":"<<batch<<",\"batch_limit\":"<<batch_limit<<",\"verified_words\":"<<words<<",\"complete_raw_MAC_coverage\":"<<((mode=="full"||mode=="export")&&source.coefficient_windows==16?"true":"false")<<",\"warmups\":0,\"repetitions\":1,\"resident_batch_wall_sum_ms\":"<<resident_ms<<",\"admission_ms\":"<<admission_ms<<",\"request_wall_ms\":"<<request_ms<<",\"setup_ms\":"<<setup_ms<<",\"copied_bytes\":"<<total_copy<<",\"synced_bytes\":"<<total_sync<<",\"cache_hits\":"<<total_hits<<",\"warmup_copied_bytes\":0,\"hashed_outputs\":"<<backend.hashed_outputs()<<",\"hashed_bytes\":"<<backend.hashed_bytes()<<",\"export\":"<<(save?"true":"false")<<",\"direct_canonical_SHA256\":"<<(direct?"true":"false")<<",\"maximum_page_rounded_BO_bytes_estimate\":"<<finishopt::Backend::maximum_page_rounded_BO_bytes<<",\"estimate_excludes_driver_overhead\":true,\"scope\":\"Batch wall union includes necessary BO uploads, scheduling, output sync and complete canonical verification. Admission/setup separate. No invented per-window wall for overlapping windows. Not live complete layer or matched CUDA time.\"}";
    summary.close();require(bool(summary),"summary write failed");std::cout<<"PASS_FINISH_REPLAY resident_batch_wall_sum_ms="<<resident_ms<<" RESULTS="<<result<<'\n';return 0;
#else
    throw std::runtime_error("parser cannot execute hardware");
#endif
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
