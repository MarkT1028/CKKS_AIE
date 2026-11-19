#pragma once

#include <wire.hpp>
#include "../../v32_ga3_finishopt_20261110/common/sealed_sha256.hpp"
#include <algorithm>
#include <array>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <unistd.h>

namespace ga_resident {
namespace path = std::filesystem;
using ga::Tile;
using ga::check;

constexpr size_t part_bytes = 32 * (1U << 20);

struct Layer {
    unsigned towers, outputs, groups;
    unsigned blocks() const { return ((towers + 15) / 16) * 16; }
    unsigned tiles() const { return blocks() * outputs * groups; }
    uint64_t words() const { return uint64_t(towers) * 131072 * outputs * groups * 3; }
};

inline Layer layer_for(const std::string& name) {
    if (name == "ga6") return {49, 8, 4};
    check(name == "ga9", "expected ga6 or ga9");
    return {45, 4, 6};
}

inline std::string part_name(unsigned index) {
    std::ostringstream out;
    out << "parts/batch_" << std::setfill('0') << std::setw(2) << index / 32 + 1
        << "/part_" << std::setw(4) << index << ".part";
    return out.str();
}

struct Window {
    unsigned block, output;
    uint64_t offset;
    std::vector<Tile> tiles;
};

inline std::vector<Window> schedule(const Layer& layer, uint64_t& bytes) {
    std::vector<Window> windows;
    unsigned id = 0;
    bytes = 0;
    for (unsigned block = 0; block < layer.blocks(); ++block) {
        const unsigned l = std::min(16U, layer.towers - 16 * (block / 16));
        for (unsigned output = 0; output < layer.outputs; ++output) {
            windows.push_back({block, output, bytes, {}});
            for (unsigned group = 0; group < layer.groups; ++group) {
                const unsigned flags = (output ? ga::reuse_weight : 0)
                                     | (group ? ga::reuse_baby : 0);
                Tile tile{++id, ga::tile_n, l, ga::terms, group, flags, {}};
                bytes += 7 * 4 + l * 8;
                if (!output) bytes += tile.input_words() * 8;
                if (!group) bytes += tile.input_words() * 8;
                windows.back().tiles.push_back(std::move(tile));
            }
        }
    }
    bytes += sizeof(ga::stop);
    return windows;
}

inline bool valid_digest(const std::string& digest) {
    return digest.size() == 64 && digest.find_first_not_of("0123456789abcdef") == std::string::npos;
}

class Source {
    const path::path root;
    const std::string layer_name;
    const finishsha::Engine& hash;
    uint64_t total, offset = 0;
    struct Part {
        std::vector<char> bytes;
        double read_ms = 0, hash_ms = 0;
        unsigned retire_failures = 0;
    };
    size_t loaded = size_t(-1), pending = size_t(-1);
    std::vector<std::string> part_hashes;
    Part current, next;
    std::unique_ptr<boexp::Worker> reader;

    void load_part(size_t index, Part& part) const {
        const auto relative = part_name(index);
        const auto file = root / relative;
        const auto size = std::min<uint64_t>(part_bytes, total - index * uint64_t(part_bytes));
        part.bytes.resize(size);
        {
            const auto start = boexp::Clock::now();
            if (ga_stream::enabled()) {
                ga_stream::fetch(layer_name, relative, {{part.bytes.data(), part.bytes.size()}});
            } else {
                check(path::is_regular_file(file) && !path::is_symlink(file)
                      && path::file_size(file) == size, ("invalid input part " + file.string()).c_str());
                std::ifstream stream(file, std::ios::binary);
                stream.read(part.bytes.data(), part.bytes.size());
                check(bool(stream) && stream.peek() == std::char_traits<char>::eof() && !stream.bad(),
                      "part length changed");
            }
            part.read_ms = boexp::elapsed(start, boexp::Clock::now());
        }
        const auto start = boexp::Clock::now();
        check(hash.hex(nullptr, 0, part.bytes.data(), part.bytes.size()) == part_hashes.at(index),
              ("input part SHA256 mismatch " + file.string()).c_str());
        part.hash_ms = boexp::elapsed(start, boexp::Clock::now());
        part.retire_failures = 0;
#ifndef GA_RESIDENT_MODEL
        if (!ga_stream::enabled()) {
            const int fd = ::open(file.c_str(), O_RDONLY | O_CLOEXEC);
            if (fd < 0) {
                ++part.retire_failures;
            } else {
                if (::posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED) != 0) ++part.retire_failures;
                ::close(fd);
            }
        }
#endif
    }

    void select_part(size_t index) {
        if (pending == index) {
            const auto start = boexp::Clock::now();
            reader->wait();
            prefetch_wait_ms += boexp::elapsed(start, boexp::Clock::now());
            std::swap(current, next);
            pending = size_t(-1);
            ++prefetched_parts;
        } else {
            check(pending == size_t(-1), "prefetched parts must be consumed in order");
            load_part(index, current);
        }

        loaded = index;
        read_ms += current.read_ms;
        hash_ms += current.hash_ms;
        retire_failures += current.retire_failures;
        part_read_bytes += current.bytes.size();
        ++parts_read;
        if (reader && index + 1 < part_hashes.size()) {
            pending = index + 1;
            reader->submit([this, following = index + 1] { load_part(following, next); });
        }
    }

    void read(void* destination, size_t bytes) {
        check(offset <= total && bytes <= total - offset, "input exceeds sealed byte count");
        auto* out = static_cast<char*>(destination);
        while (bytes) {
            const size_t index = offset / part_bytes, position = offset % part_bytes;
            if (loaded != index) select_part(index);
            const size_t span = std::min(bytes, current.bytes.size() - position);
            std::memcpy(out, current.bytes.data() + position, span);
            out += span;
            offset += span;
            bytes -= span;
        }
    }

    void admit_payload(const Tile& tile, std::vector<uint64_t>& buffer) {
        buffer.resize(tile.input_words());
        const size_t bytes = buffer.size() * sizeof(uint64_t);
        read(buffer.data(), bytes);
        ga::input_range(tile, buffer.data());
        admitted_payload_bytes += bytes;
    }

public:
    std::vector<std::string> output_hashes;
    std::array<std::vector<uint64_t>, ga::weight_slots> weights;
    std::vector<uint64_t> baby;
    uint64_t part_read_bytes = 0, admitted_payload_bytes = 0;
    unsigned parts_read = 0, retire_failures = 0, prefetched_parts = 0;
    double read_ms = 0, hash_ms = 0, prefetch_wait_ms = 0;

    Source(const path::path& root, const std::string& layer, const path::path& index, const finishsha::Engine& hash,
           uint64_t total, unsigned tiles, bool prefetch = false)
        : root(root), layer_name(layer), hash(hash), total(total) {
        std::ifstream manifest(index);
        uint64_t indexed_bytes = 0;
        check(bool(manifest >> indexed_bytes) && indexed_bytes == total, "sealed input size mismatch");
        for (size_t i = 0; i < (total + part_bytes - 1) / part_bytes; ++i) {
            std::string digest;
            check(bool(manifest >> digest) && valid_digest(digest), "invalid sealed input digest");
            part_hashes.push_back(std::move(digest));
        }
        for (unsigned i = 0; i < tiles; ++i) {
            std::string digest;
            check(bool(manifest >> digest) && valid_digest(digest), "invalid sealed output digest");
            output_hashes.push_back(std::move(digest));
        }
        std::string extra;
        check(!(manifest >> extra), "extra sealed index entries");
        if (prefetch) reader = std::make_unique<boexp::Worker>();
    }

    void admit(Window& window) {
        offset = window.offset;
        for (auto& tile : window.tiles) {
            std::array<uint32_t, 7> header{};
            read(header.data(), sizeof(header));
            check(header == std::array<uint32_t, 7>{ga::request, tile.id, tile.n, tile.l,
                                                    tile.k, tile.slot, tile.flags},
                  "wire header differs from sealed tile schedule");
            tile.q.resize(tile.l);
            read(tile.q.data(), tile.l * sizeof(uint64_t));
            tile.validate();
            check(tile.same_shape(window.tiles.front()), "moduli differ within window");
            if (!(tile.flags & ga::reuse_weight)) admit_payload(tile, weights[tile.slot]);
            if (!(tile.flags & ga::reuse_baby)) admit_payload(tile, baby);
        }
    }

    void check_end() {
        uint32_t stop = 0;
        read(&stop, sizeof(stop));
        check(stop == ga::stop && offset == total, "invalid end of sealed wire stream");
    }
};
}
