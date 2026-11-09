#include "../../../board_packages/v32_ga3_20261104/common/finish_overlap.hpp"
#include <algorithm>
#include <iostream>
struct Fake {
 std::string fault;std::array<unsigned,2> owner{99,99};std::array<bool,2> finished{true,true};bool active=false;unsigned completions=0;
 void fail(const char*s){if(fault==s)throw std::runtime_error(s);}
 void prepare(unsigned i,unsigned b,boexp::Frame&,boexp::Clock::time_point){fail("prepare");if(i==1)fail("prepare_worker");boexp::ensure(finished[b],"premature bank reuse");owner[b]=i;finished[b]=false;}
 void start(unsigned i,unsigned b){fail("start");boexp::ensure(!active&&owner[b]==i&&!finished[b],"overlapping graph start/incorrect bank");active=true;}
 void wait(unsigned,unsigned){fail("wait");boexp::ensure(active,"wait without invocation");}
 void complete(unsigned,unsigned,boexp::Frame&,boexp::Clock::time_point){fail("complete");boexp::ensure(active,"status outside active invocation");active=false;++completions;}
 void finish(unsigned i,unsigned b,boexp::Frame&,boexp::Clock::time_point){fail("finish");boexp::ensure(owner[b]==i&&!finished[b],"finish ownership");finished[b]=true;}
 void save(unsigned,unsigned){fail("save");}
 void cancel()noexcept{active=false;}
};
int main(){for(const auto* f:{"","prepare","prepare_worker","start","wait","complete","finish","save"}){Fake fake;fake.fault=f;boexp::Worker worker;bool failed=false;try{auto replay=boexp::run_finish_overlap(fake,17,worker,true);boexp::ensure(replay.frames.size()==17&&fake.completions==17,"missing jobs");}catch(...){failed=true;}boexp::ensure(failed==!fake.fault.empty(),"injected fault not propagated");worker.close();boexp::ensure(!fake.active,"active invocation leaked");}std::cout<<"PASS_PIPELINE_BANK_OWNERSHIP_AND_SEVEN_FAILURE_PATHS\n";}
