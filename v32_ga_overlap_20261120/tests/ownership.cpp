#include "../common/three_bank.hpp"
#include <cassert>
#include <iostream>

namespace {
struct Model {
    enum State {free,ready,running,done};
    std::array<State,3> state{free,free,free};
    std::mutex mu;
    std::condition_variable signal;
    int active=-1;
    unsigned verified=0,saved=0,count;
    bool third_prepared=false,cancelled=false;
    int fault;

    Model(unsigned count,int fault):count(count),fault(fault) {}
    void prepare(unsigned i,unsigned b,boexp::Frame&,boexp::Clock::time_point) {
        std::lock_guard<std::mutex> lock(mu);
        assert(b==i%3 && state[b]==free);
        if (i==2 && fault==1) throw std::runtime_error("prepare");
        state[b]=ready;
        if (i==2) {third_prepared=true;signal.notify_all();}
    }
    void start(unsigned i,unsigned b) {
        std::lock_guard<std::mutex> lock(mu);
        assert(active==-1 && state[b]==ready);
        active=int(i);
        state[b]=running;
    }
    void wait(unsigned i,unsigned b) {
        std::lock_guard<std::mutex> lock(mu);
        assert(active==int(i) && state[b]==running);
    }
    void complete(unsigned i,unsigned b,boexp::Frame&,boexp::Clock::time_point) {
        std::lock_guard<std::mutex> lock(mu);
        assert(active==int(i) && state[b]==running);
        active=-1; state[b]=done;
    }
    void finish(unsigned i,unsigned b,boexp::Frame&,boexp::Clock::time_point) {
        std::unique_lock<std::mutex> lock(mu);
        assert(i==verified && state[b]==done);
        assert(active==(i+1<count?int(i+1):-1));
        if (i==0 && count>=3 && fault!=1) {
            const bool prepared=signal.wait_for(lock,std::chrono::seconds(5),[&]{return third_prepared;});
            assert(prepared && state[2]==ready && state[1]==running);
        }
        if (i==1 && fault==2) throw std::runtime_error("finish");
        state[b]=free; ++verified;
    }
    void save(unsigned i,unsigned) {assert(i==saved++ && verified==i+1);}
    void cancel() {cancelled=true;}
};
}

int main() {
    for (unsigned n : {1U,2U,3U,4U,16U}) {
        Model model(n,0);
        boexp::Worker worker;
        boexp::run_three_bank(model,n,worker,true);
        assert(model.verified==n && model.saved==n && !model.cancelled);
    }
    for (int failure : {1,2}) {
        Model model(4,failure);
        boexp::Worker worker;
        try {boexp::run_three_bank(model,4,worker,false);assert(false);}
        catch (const std::runtime_error& e) {
            assert(model.cancelled && std::string(e.what())==(failure==1?"prepare":"finish"));
        }
    }
    std::cout<<"PASS_THREE_BANK_OWNERSHIP_AND_FAULTS\n";
}
