#pragma once
#include <adf.h>
#include <aie_api/aie.hpp>
#ifndef PERF_AIE_CORES
#define PERF_AIE_CORES 1
#endif
#ifndef PERF_COMPACT
#define PERF_COMPACT 0
#endif
#if PERF_COMPACT
void limb_diag(adf::input_buffer<int16>&,adf::input_buffer<int16>&,adf::output_buffer<uint32>&);
#else
void limb_mul(adf::input_buffer<int16>&,adf::input_buffer<int16>&,adf::output_buffer<int32>&);
#endif
class PerfGraph:public adf::graph {
public:
    adf::input_plio left[PERF_AIE_CORES],right[PERF_AIE_CORES];
    adf::output_plio partials[PERF_AIE_CORES];
    adf::kernel mul[PERF_AIE_CORES];
    PerfGraph() {
        for(unsigned c=0;c<PERF_AIE_CORES;++c) {
            std::string suffix=std::to_string(c);
            left[c]=adf::input_plio::create("ckks_left_"+suffix,adf::plio_128_bits,"data/left"+suffix+".txt",225);
            right[c]=adf::input_plio::create("ckks_right_"+suffix,adf::plio_128_bits,"data/right"+suffix+".txt",225);
            partials[c]=adf::output_plio::create("ckks_partials_"+suffix,adf::plio_128_bits,"data/partials"+suffix+".txt",225);
#if PERF_COMPACT
            mul[c]=adf::kernel::create(limb_diag);
            adf::source(mul[c])="limb_diag.cpp";
            adf::dimensions(mul[c].out[0])={448};
#else
            mul[c]=adf::kernel::create(limb_mul);
            adf::source(mul[c])="limb_mul.cpp";
            adf::dimensions(mul[c].out[0])={1024};
#endif
            adf::runtime<adf::ratio>(mul[c])=.9;
#ifndef __X86SIM__
            adf::location<adf::kernel>(mul[c])=adf::tile(17+c,0);
#endif
            adf::connect<>(left[c].out[0],mul[c].in[0]);
            adf::connect<>(right[c].out[0],mul[c].in[1]);
            adf::connect<>(mul[c].out[0],partials[c].in[0]);
            adf::dimensions(mul[c].in[0])={256};
            adf::dimensions(mul[c].in[1])={256};
        }
    }
};
