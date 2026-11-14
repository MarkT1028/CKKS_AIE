#pragma once

#include <wire.hpp>
#include "../v32_ga3_finishopt_20261110/common/sealed_sha256.hpp"
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
    const finishsha::Engine& hash;
    uint64_t total, offset = 0;
    size_t loaded = size_t(-1);
    std::vector<std::string> part_hashes;
    std::vector<char> part;

    void load_part(size_t index) {
        const auto file = root / part_name(index);
        const auto size = std::min<uint64_t>(part_bytes, total - index * uint64_t(part_bytes));
        check(path::is_regular_file(file) && !path::is_symlink(file)
              && path::file_size(file) == size, ("invalid input part " + file.string()).c_str());
        part.resize(size);
        {
            std::ifstream stream(file, std::ios::binary);
            const auto read_start = boexp::Clock::now();
            stream.read(part.data(), part.size());
            check(bool(stream) && stream.peek() == std::char_traits<char>::eof() && !stream.bad(),
                  "part length changed");
            read_ms += boexp::elapsed(read_start, boexp::Clock::now());
        }
        const auto hash_start = boexp::Clock::now();
        check(hash.hex(nullptr, 0, part.data(), part.size()) == part_hashes.at(index),
              ("input part SHA256 mismatch " + file.string()).c_str());
        hash_ms += boexp::elapsed(hash_start, boexp::Clock::now());
#ifndef GA_RESIDENT_MODEL
        // Advise retirement only for this input part, after hashing its bytes.
        const int fd = ::open(file.c_str(), O_RDONLY | O_CLOEXEC);
        if (fd < 0) {
            ++retire_failures;
        } else {
            if (::posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED) != 0) ++retire_failures;
            ::close(fd);
        }
#endif
        part_read_bytes += size;
        ++parts_read;
        loaded = index;
    }

    void read(void* destination, size_t bytes) {
        check(offset <= total && bytes <= total - offset, "input exceeds sealed byte count");
        auto* out = static_cast<char*>(destination);
        while (bytes) {
            const size_t index = offset / part_bytes, position = offset % part_bytes;
            if (loaded != index) load_part(index);
            const size_t span = std::min(bytes, part.size() - position);
            std::memcpy(out, part.data() + position, span);
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
    unsigned parts_read = 0, retire_failures = 0;
    double read_ms = 0, hash_ms = 0;

    Source(const path::path& root, const path::path& index, const finishsha::Engine& hash,
           uint64_t total, unsigned tiles)
        : root(root), hash(hash), total(total) {
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
