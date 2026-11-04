#pragma once
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <exception>
#include <functional>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace boexp {
using Clock=std::chrono::steady_clock;
inline double elapsed(Clock::time_point a,Clock::time_point b){return std::chrono::duration<double,std::milli>(b-a).count();}
inline void ensure(bool value,const char* msg){if(!value)throw std::runtime_error(msg);}
struct Span {const char* name="";int lane=-1;double begin=0,end=0;};
struct Frame {
    unsigned chunk=0,bank=0,count=0;
    std::array<Span,64> spans{};
    template<class Fn> void timed(const char* name,int lane,Clock::time_point epoch,Fn fn){
        ensure(count<spans.size(),"trace capacity exceeded");auto start=Clock::now();
        try{fn();}catch(const std::exception& e){throw std::runtime_error("chunk="+std::to_string(chunk)+" bank="+std::to_string(bank)+" stage="+name+" lane="+std::to_string(lane)+": "+e.what());}
        auto end=Clock::now();
        spans[count++]={name,lane,elapsed(epoch,start),elapsed(epoch,end)};
    }
    double total(const char* name) const {double sum=0;for(unsigned i=0;i<count;++i)if(std::string(spans[i].name)==name)sum+=spans[i].end-spans[i].begin;return sum;}
};

// One persistent worker, with at most one preparation job outstanding.
// wait() transfers the completed job's exception to the controller thread.
class Worker {
    std::mutex mutex;std::condition_variable ready,done;
    bool stopping=false,pending=false,complete=false;
    std::function<void()> job;std::exception_ptr error;
    std::thread thread;
    void loop(){
        std::unique_lock<std::mutex> lock(mutex);
        for(;;){ready.wait(lock,[&]{return stopping||bool(job);});if(stopping&&!job)return;
            auto next=std::move(job);job={};lock.unlock();std::exception_ptr fault;
            try{next();}catch(...){fault=std::current_exception();}
            lock.lock();error=fault;complete=true;done.notify_all();
        }
    }
public:
    Worker():thread([this]{loop();}){}
    Worker(const Worker&)=delete;Worker& operator=(const Worker&)=delete;
    void submit(std::function<void()> fn){std::lock_guard<std::mutex> lock(mutex);ensure(!stopping&&!pending,"preparation worker already occupied");pending=true;complete=false;error=nullptr;job=std::move(fn);ready.notify_one();}
    void wait(){std::unique_lock<std::mutex> lock(mutex);ensure(pending,"no preparation to wait for");done.wait(lock,[&]{return complete;});auto fault=error;pending=false;complete=false;error=nullptr;lock.unlock();if(fault)std::rethrow_exception(fault);}
    void close() noexcept {{std::lock_guard<std::mutex> lock(mutex);stopping=true;}ready.notify_all();if(thread.joinable())thread.join();}
    ~Worker(){close();}
};
enum class State {Free,Preparing,Ready,Running};
struct Replay {std::vector<Frame> frames;double wall_ms=0;};

// Hardware and the independent host-only test model execute this SAME schedule.
// Only next-chunk preparation overlaps run/wait. Graphs/CUs are never launched
// concurrently, and a bank remains owned until readback+full verification ends.
template<class Backend>
Replay run(Backend& backend,unsigned chunks,Worker* worker,bool save_outputs){
    ensure(chunks>0,"empty replay");Replay result;result.frames.resize(chunks);
    std::array<std::atomic<State>,2> state;state[0]=State::Free;state[1]=State::Free;
    auto epoch=Clock::now();
    auto transition=[&](unsigned bank,State from,State to){ensure(state[bank].compare_exchange_strong(from,to),"BO bank ownership violation");};
    auto prepare=[&](unsigned index,unsigned bank){transition(bank,State::Free,State::Preparing);auto& frame=result.frames[index];frame.chunk=index;frame.bank=bank;backend.prepare(index,bank,frame,epoch);transition(bank,State::Preparing,State::Ready);};
    try{
        prepare(0,0);
        for(unsigned index=0;index<chunks;++index){
            unsigned bank=worker?index%2:0;
            if(worker&&index>0)worker->wait();
            transition(bank,State::Ready,State::Running);auto& frame=result.frames[index];
            frame.timed("execute",-1,epoch,[&]{
                backend.start(index,bank);
                if(worker&&index+1<chunks){auto next=index+1;worker->submit([&,next]{prepare(next,next%2);});}
                backend.wait(index,bank);
            });
            backend.finish(index,bank,frame,epoch);
            if(save_outputs)frame.timed("output_save",-1,epoch,[&]{backend.save(index,bank);});
            transition(bank,State::Running,State::Free);
            if(!worker&&index+1<chunks)prepare(index+1,0);
        }
        result.wall_ms=elapsed(epoch,Clock::now());return result;
    }catch(...){backend.cancel();if(worker)worker->close();throw;}
}

// Disjoint, exact half-coefficient partitions. InputCase was admitted by the
// unchanged canonical parser; every call still validates shape, bounds, alias.
template<class Input>
void split_to(const Input& in,unsigned lane,uint64_t* destination,size_t words){
    ensure(lane<2&&in.n>=128&&in.n<=8192&&(in.n&(in.n-1))==0,"invalid mapped split");
    ensure(in.l>=1&&in.l<=16&&in.k>=1&&in.k<=16&&in.parameters.size()==in.l,"invalid mapped shape");
    ensure(in.words.size()==size_t(in.n)*in.l*in.k*4&&words==in.words.size()/2&&destination,"mapped split length");
    auto source_begin=reinterpret_cast<uintptr_t>(in.words.data()),source_end=source_begin+in.words.size()*sizeof(uint64_t);
    auto target_begin=reinterpret_cast<uintptr_t>(destination),target_end=target_begin+words*sizeof(uint64_t);
    ensure(target_end>=target_begin&&(target_end<=source_begin||target_begin>=source_end),"overlapping mapped split");
    size_t half=in.n/2,block=half*4;
    for(unsigned pair=0;pair<in.k;++pair)for(unsigned tower=0;tower<in.l;++tower){size_t i=size_t(pair)*in.l+tower;std::copy_n(in.words.data()+(i*in.n+lane*half)*4,block,destination+i*block);}
}
template<class Input>
void merge_from(const Input& in,unsigned lane,const uint64_t* source,size_t words,std::vector<uint64_t>& out){
    ensure(lane<2&&source&&words==size_t(in.n/2)*in.l*3&&out.size()==in.output_words(),"mapped merge shape");
    size_t half=in.n/2;
    for(unsigned tower=0;tower<in.l;++tower)std::copy_n(source+size_t(tower)*half*3,half*3,out.data()+(size_t(tower)*in.n+lane*half)*3);
}
}
