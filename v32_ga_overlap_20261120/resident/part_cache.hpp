#pragma once
#include <array>
#include <fstream>

namespace ga_resident {
// The last, incomplete 8-byte word is always stored verbatim.
inline void decode_part(const std::filesystem::path& path, std::vector<char>& output,
                        double& read_ms, double& decode_ms, uint64_t& stored) {
    constexpr size_t block_size = 32768;
    std::array<char,block_size> packed;
    std::ifstream input(path, std::ios::binary);
    ga::check(bool(input), "open compact input part");
    auto read = [&](char* target, size_t count) {
        auto tick = boexp::Clock::now();
        input.read(target,count);
        read_ms += boexp::elapsed(tick,boexp::Clock::now());
        ga::check(bool(input), "truncated compact input part");
        stored += count;
    };
    std::array<char,16> header;
    read(header.data(),header.size());
    uint64_t size;
    std::memcpy(&size,header.data()+8,sizeof(size));
    ga::check(std::memcmp(header.data(),"GAPLAN01",8)==0 && size==output.size(),
              "invalid compact input identity or length");
    for (size_t at=0; at<size; at+=block_size) {
        size_t n=std::min<size_t>(size-at,block_size), words=n/8;
        std::array<unsigned char,9> lanes;
        read(reinterpret_cast<char*>(lanes.data()),lanes.size());
        char* out=output.data()+at;
        unsigned mask=lanes[0];
        if (mask==255) {
            read(out,n);
            continue;
        }
        size_t payload = words * unsigned(__builtin_popcount(mask)) + n%8;
        read(packed.data(),payload);
        const auto tick=boexp::Clock::now();
        const char* in=packed.data();
        for (unsigned lane=0; lane<8; ++lane) {
            if (mask & (1U<<lane)) {
                for (size_t i=0; i<words; ++i) out[8*i+lane]=in[i];
                in+=words;
            } else {
                for (size_t i=0; i<words; ++i) out[8*i+lane]=char(lanes[lane+1]);
            }
        }
        std::memcpy(out+8*words,in,n%8);
        decode_ms+=boexp::elapsed(tick,boexp::Clock::now());
    }
    ga::check(input.peek()==std::char_traits<char>::eof() && !input.bad(),
              "trailing bytes or error in compact input part");
}
}
