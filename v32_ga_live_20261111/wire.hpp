#pragma once
#include <cstdint>
#include <istream>
#include <ostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace ga {
constexpr uint32_t hello = 0x47413148, request = 0x47413151, reply = 0x47413152, stop = 0x47413153;
constexpr unsigned tile_n = 8192, tile_l = 16, terms = 16, weight_slots = 6;
constexpr unsigned reuse_weight = 1, reuse_baby = 2;
inline void check(bool ok, const char* what) { if (!ok) throw std::runtime_error(what); }
template<class T> void write(std::ostream& out, const T& value) {
    out.write(reinterpret_cast<const char*>(&value), sizeof(T));
    check(bool(out), "write protocol field");
}
template<class T> T read(std::istream& in) {
    T value{};
    in.read(reinterpret_cast<char*>(&value), sizeof(T));
    check(bool(in), "truncated protocol field");
    return value;
}
inline void write_words(std::ostream& out, const uint64_t* data, size_t words) {
    out.write(reinterpret_cast<const char*>(data), words * sizeof(uint64_t));
    check(bool(out), "write residue payload");
}
inline void read_words(std::istream& in, uint64_t* data, size_t words) {
    in.read(reinterpret_cast<char*>(data), words * sizeof(uint64_t));
    check(bool(in), "truncated residue payload");
}
inline void little_endian() {
    const uint32_t one = 1;
    check(*reinterpret_cast<const unsigned char*>(&one) == 1, "little endian host required");
}
struct Tile {
    uint32_t id, n, l, k, slot, flags;
    std::vector<uint64_t> q;
    size_t input_words() const { return size_t(n) * l * k * 2; }
    size_t output_words() const { return size_t(n) * l * 3; }
    void validate() const {
        check(n >= 128 && n <= tile_n && !(n & (n - 1)), "unsupported tile N");
        check(l && l <= tile_l && k && k <= terms && slot < weight_slots && flags <= 3, "unsupported tile shape or reuse flags");
        check(q.size() == l, "modulus count");
        for (auto p : q) check(p >= (1ULL << 44) && p < (1ULL << 60) && (p & 1), "modulus outside PL contract");
    }
    bool same_shape(const Tile& other) const { return n == other.n && l == other.l && k == other.k && q == other.q; }
};
inline void send_tile(std::ostream& out, const Tile& t) {
    t.validate();
    for (uint32_t value : {request, t.id, t.n, t.l, t.k, t.slot, t.flags}) write(out, value);
    write_words(out, t.q.data(), t.q.size());
}
inline Tile receive_tile(std::istream& in) {
    Tile t{};
    t.id=read<uint32_t>(in); t.n=read<uint32_t>(in); t.l=read<uint32_t>(in);
    t.k=read<uint32_t>(in); t.slot=read<uint32_t>(in); t.flags=read<uint32_t>(in);
    check(t.l && t.l <= tile_l, "invalid modulus count");
    t.q.resize(t.l); read_words(in,t.q.data(),t.l); t.validate(); return t;
}
inline void input_range(const Tile& t, const uint64_t* values) {
    size_t offset=0;
    for (unsigned k=0; k<t.k; ++k) for (auto q:t.q) {
        for (unsigned j=0; j<t.n*2; ++j) check(values[offset+j]<q,"noncanonical input residue");
        offset+=t.n*2;
    }
}
}
