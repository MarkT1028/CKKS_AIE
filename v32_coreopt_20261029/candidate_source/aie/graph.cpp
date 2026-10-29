#include "graph.hpp"
#ifndef PERF_FRAMES
#define PERF_FRAMES 1
#endif
PerfGraph ckks_graph;
#if defined(__AIESIM__) || defined(__X86SIM__)
int main(){ckks_graph.init();ckks_graph.run(PERF_FRAMES);ckks_graph.end();return 0;}
#endif
