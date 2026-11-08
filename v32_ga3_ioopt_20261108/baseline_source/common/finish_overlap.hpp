#pragma once
#include "replay.hpp"

namespace boexp {
enum class FinishState {Free,Preparing,Ready,Running,Completed};

// Two disjoint BO banks, ONE graph/CU launch active at a time.
// After wait + status checks, launch i+1 BEFORE merging/checking i.
// A bank becomes reusable only after its full verification (and export).
// The existing preparation worker is never used for readback or another job
// concurrently; after finish(i), it may prepare i+2 into that released bank.
template<class Backend>
Replay run_finish_overlap(Backend& backend,unsigned chunks,Worker& worker,bool save_outputs){
    ensure(chunks>0,"empty finish-overlap replay");Replay result;result.frames.resize(chunks);
    std::array<std::atomic<FinishState>,2> state;state[0]=FinishState::Free;state[1]=FinishState::Free;
    std::vector<unsigned> execute_slot(chunks);const auto epoch=Clock::now();
    auto transition=[&](unsigned b,FinishState from,FinishState to){ensure(state[b].compare_exchange_strong(from,to),"finish-overlap bank ownership violation");};
    auto prepare=[&](unsigned i){unsigned b=i%2;transition(b,FinishState::Free,FinishState::Preparing);
        auto& frame=result.frames[i];frame.chunk=i;frame.bank=b;backend.prepare(i,b,frame,epoch);
        transition(b,FinishState::Preparing,FinishState::Ready);};
    auto start=[&](unsigned i){auto& frame=result.frames[i];transition(i%2,FinishState::Ready,FinishState::Running);
        ensure(frame.count<frame.spans.size(),"execute trace capacity");unsigned slot=frame.count++;execute_slot[i]=slot;
        frame.spans[slot]={"execute",-1,elapsed(epoch,Clock::now()),0};backend.start(i,i%2);};
    try{
        prepare(0);start(0);
        if(chunks>1)worker.submit([&]{prepare(1);});
        for(unsigned i=0;i<chunks;++i){
            auto& frame=result.frames[i];const unsigned b=i%2;
            backend.wait(i,b);frame.spans[execute_slot[i]].end=elapsed(epoch,Clock::now());
            backend.complete(i,b,frame,epoch); // Read old invocation's status BEFORE another launch.
            transition(b,FinishState::Running,FinishState::Completed);
            if(i+1<chunks){worker.wait();start(i+1);}
            backend.finish(i,b,frame,epoch);
            if(save_outputs)frame.timed("output_save",-1,epoch,[&]{backend.save(i,b);});
            transition(b,FinishState::Completed,FinishState::Free);
            if(i+2<chunks){const unsigned next=i+2;worker.submit([&,next]{prepare(next);});}
        }
        result.wall_ms=elapsed(epoch,Clock::now());return result;
    }catch(...){backend.cancel();worker.close();throw;}
}
}
