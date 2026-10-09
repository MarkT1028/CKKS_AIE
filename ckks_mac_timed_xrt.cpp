#include <array>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <sstream>
#include <string>
#include <system_error>
#include <vector>

#ifndef CKKSMAC_PARSER_ONLY
#if __has_include(<xrt/detail/ert.h>)
#include <xrt/detail/ert.h>
#else
#include <ert.h>
#endif
#include <xrt/xrt_bo.h>
#include <xrt/xrt_device.h>
#include <xrt/xrt_graph.h>
#include <xrt/xrt_kernel.h>
#include <xrt/experimental/xrt_ini.h>
#endif

namespace fs = std::filesystem;
__extension__ typedef unsigned __int128 U128;

namespace {

constexpr uint32_t kFormatVersion = 1;
constexpr uint32_t kInputKind = 1;
constexpr uint32_t kOutputKind = 2;
constexpr uint32_t kTile = 64;
constexpr uint32_t kMaxN = 8192;
constexpr uint32_t kMaxL = 16;
constexpr uint32_t kMaxK = 16;

void require(bool condition, const std::string& message) {
    if (!condition)
        throw std::runtime_error(message);
}

uint64_t checked_mul(uint64_t a, uint64_t b, const char* label) {
    require(a == 0 || b <= std::numeric_limits<uint64_t>::max() / a,
            std::string("size overflow: ") + label);
    return a * b;
}

uint64_t read_le(std::istream& stream, unsigned bytes) {
    uint64_t value = 0;
    for (unsigned i = 0; i < bytes; ++i) {
        const int byte = stream.get();
        require(byte != EOF, "truncated CKKSMAC1 file");
        value |= uint64_t(static_cast<unsigned char>(byte)) << (8 * i);
    }
    return value;
}

constexpr const char* kBootUuid = "1b664c9b428c5972904d75ffc08ea5df";

// This host accepts only metadata for the matching boot-programmed design.
// Check the DT marker before creating an XRT device or touching CU registers.
void validate_boot_marker(const fs::path& path =
    "/sys/firmware/devicetree/base/chosen/ckks,boot-xclbin-uuid") {
    std::ifstream stream(path, std::ios::binary);
    require(bool(stream), "CKKS boot marker missing; boot the supplied CKKS image first");
    const std::string marker((std::istreambuf_iterator<char>(stream)),
                             std::istreambuf_iterator<char>());
    require(marker == std::string(kBootUuid) + '\0',
            "CKKS boot marker does not match this host/xclbin; refusing CU access");
    std::cout << "PASS boot marker matches CKKS hardware\n" << std::flush;
}

void validate_boot_xclbin(const fs::path& path) {
    std::ifstream stream(path, std::ios::binary);
    require(bool(stream), "cannot open xclbin: " + path.string());
    const auto size = fs::file_size(path);
    require(size >= 456, "truncated xclbin header");
    std::array<char, 8> magic{};
    stream.read(magic.data(), magic.size());
    require(magic == std::array<char, 8>{'x','c','l','b','i','n','2','\0'},
            "invalid xclbin magic");
    stream.seekg(304);
    require(read_le(stream, 8) == size, "xclbin length mismatch");
    stream.seekg(332);
    const auto mode = read_le(stream, 2);
    const auto actions = read_le(stream, 2);
    require(mode == 0 && actions == 0,
            "expected flat boot-programmed metadata with action_mask=0; "
            "refusing hardware reload");
    stream.seekg(416);
    std::ostringstream uuid;
    for (unsigned i = 0; i < 16; ++i)
        uuid << std::hex << std::setfill('0') << std::setw(2) << read_le(stream, 1);
    require(uuid.str() == kBootUuid, "xclbin UUID does not match CKKS boot image");
    stream.seekg(448);
    const auto count = read_le(stream, 4);
    require(count > 0 && count <= 1024 && 456 + count * 40 <= size,
            "invalid xclbin section table");
    bool has_aie = false, has_resources = false, has_ip = false;
    for (uint64_t i = 0; i < count; ++i) {
        stream.seekg(static_cast<std::streamoff>(456 + i * 40));
        const auto kind = read_le(stream, 4);
        stream.seekg(20, std::ios::cur);  // section name and alignment padding
        const auto offset = read_le(stream, 8);
        const auto length = read_le(stream, 8);
        require(offset >= 456 + count * 40 && offset <= size && length <= size - offset,
                "xclbin section exceeds file bounds");
        require(kind != 0 && kind != 18 && kind != 19 && kind != 20 &&
                    kind != 30 && kind != 32,
                "boot metadata must not contain PDI, BITSTREAM, partition or overlay");
        has_ip |= kind == 8;
        has_aie |= kind == 25;
        has_resources |= kind == 29;
    }
    require(has_ip && has_aie && has_resources,
            "missing kernel layout or packaged AIE resources");
    std::cout << "PASS xclbin mode=flat action_mask=0 boot_programmed uuid="
              << uuid.str() << "\n" << std::flush;
}

#ifndef CKKSMAC_PARSER_ONLY
void write_le(std::ostream& stream, uint64_t value, unsigned bytes) {
    for (unsigned i = 0; i < bytes; ++i)
        stream.put(static_cast<char>((value >> (8 * i)) & 0xff));
    require(bool(stream), "failed to write output file");
}
#endif

struct Parameter {
    uint64_t q = 0;
    uint64_t mu_lo = 0;
    uint64_t mu_hi = 0;
};

struct InputCase {
    uint32_t n = 0;
    uint32_t l = 0;
    uint32_t k = 0;
    std::vector<Parameter> parameters;
    std::vector<uint64_t> words;

    uint64_t frames() const {
        return checked_mul(checked_mul(checked_mul(l, n / kTile, "frames"), k,
                                       "frames"),
                           4, "frames");
    }

    uint64_t output_words() const {
        return checked_mul(checked_mul(n, l, "output words"), 3,
                           "output words");
    }
};

bool is_power_of_two(uint32_t value) {
    return value != 0 && (value & (value - 1)) == 0;
}

void validate_parameter(const Parameter& parameter, uint32_t tower) {
    require(parameter.q >= (uint64_t(1) << 48) &&
                parameter.q < (uint64_t(1) << 60) && (parameter.q & 1),
            "invalid modulus at tower " + std::to_string(tower));
    const U128 expected = (~U128(0)) / parameter.q;
    require(parameter.mu_lo == uint64_t(expected) &&
                parameter.mu_hi == uint64_t(expected >> 64),
            "invalid reciprocal at tower " + std::to_string(tower));
    require((parameter.mu_hi >> 17) == 0,
            "reciprocal exceeds the 81-bit hardware contract at tower " +
                std::to_string(tower));
}

InputCase read_input(const fs::path& path) {
    std::ifstream stream(path, std::ios::binary);
    require(bool(stream), "cannot open input file: " + path.string());

    char magic[8] = {};
    stream.read(magic, sizeof(magic));
    require(stream.gcount() == 8 && std::string(magic, 8) == "CKKSMAC1",
            "bad CKKSMAC1 magic");

    std::array<uint32_t, 10> header{};
    for (auto& value : header)
        value = static_cast<uint32_t>(read_le(stream, 4));

    require(header[0] == kFormatVersion, "unsupported CKKSMAC1 version");
    require(header[1] == kInputKind, "expected an input record");
    require(header[5] == 4, "input must contain four ciphertext components");
    require(header[6] == 1 && header[7] == kTile && header[8] == 0 &&
                header[9] == 0,
            "unsupported CKKSMAC1 layout");

    InputCase result;
    result.n = header[2];
    result.l = header[3];
    result.k = header[4];
    require(result.n >= kTile && result.n <= kMaxN &&
                is_power_of_two(result.n),
            "N must be a power of two in [64, 8192]");
    require(result.l >= 1 && result.l <= kMaxL, "L must be in [1, 16]");
    require(result.k >= 1 && result.k <= kMaxK, "K must be in [1, 16]");

    const uint64_t declared_words = read_le(stream, 8);
    require(read_le(stream, 8) == 0, "reserved header word is nonzero");
    const uint64_t expected_words = checked_mul(
        checked_mul(checked_mul(result.n, result.l, "input words"), result.k,
                    "input words"),
        4, "input words");
    require(declared_words == expected_words, "input payload size mismatch");

    const uint64_t expected_bytes = 64 + checked_mul(result.l, 24, "parameters") +
                                    checked_mul(expected_words, 8, "payload");
    require(fs::file_size(path) == expected_bytes, "input file size mismatch");

    result.parameters.resize(result.l);
    for (uint32_t tower = 0; tower < result.l; ++tower) {
        auto& parameter = result.parameters[tower];
        parameter.q = read_le(stream, 8);
        parameter.mu_lo = read_le(stream, 8);
        parameter.mu_hi = read_le(stream, 8);
        validate_parameter(parameter, tower);
    }

    require(expected_words <= std::numeric_limits<size_t>::max(),
            "input payload is too large for this host");
    result.words.resize(static_cast<size_t>(expected_words));
    const uint64_t words_per_tower = checked_mul(result.n, 4, "tower words");
    for (uint64_t index = 0; index < expected_words; ++index) {
        const uint64_t value = read_le(stream, 8);
        const uint32_t tower = static_cast<uint32_t>((index / words_per_tower) % result.l);
        require(value < result.parameters[tower].q,
                "noncanonical input residue at word " + std::to_string(index));
        result.words[static_cast<size_t>(index)] = value;
    }
    require(stream.peek() == EOF, "unexpected bytes after input payload");
    return result;
}

std::vector<uint64_t> pack_parameters(const InputCase& input) {
    // The file stores 24 bytes per tower.  The generated 256-bit M_AXI port
    // addresses each ap_uint<192> element with a 32-byte stride.
    std::vector<uint64_t> packed(size_t(input.l) * 4, 0);
    for (size_t tower = 0; tower < input.parameters.size(); ++tower) {
        packed[4 * tower] = input.parameters[tower].q;
        packed[4 * tower + 1] = input.parameters[tower].mu_lo;
        packed[4 * tower + 2] = input.parameters[tower].mu_hi;
    }
    return packed;
}

#ifndef CKKSMAC_PARSER_ONLY
void write_output(const fs::path& path, const InputCase& input,
                  const std::vector<uint64_t>& words) {
    require(words.size() == input.output_words(), "hardware output size mismatch");
    require(!fs::exists(path), "output path already exists: " + path.string());

    const fs::path temporary = path.string() + ".tmp";
    require(!fs::exists(temporary), "temporary output path already exists");
    try {
        std::ofstream stream(temporary, std::ios::binary);
        require(bool(stream), "cannot create output file: " + temporary.string());
        stream.write("CKKSMAC1", 8);
        for (uint32_t value : std::array<uint32_t, 10>{
                 kFormatVersion, kOutputKind, input.n, input.l, input.k, 3, 1,
                 kTile, 0, 0})
            write_le(stream, value, 4);
        write_le(stream, words.size(), 8);
        write_le(stream, 0, 8);
        for (const auto& parameter : input.parameters) {
            write_le(stream, parameter.q, 8);
            write_le(stream, parameter.mu_lo, 8);
            write_le(stream, parameter.mu_hi, 8);
        }
        for (uint64_t value : words)
            write_le(stream, value, 8);
        stream.close();
        require(bool(stream), "failed to finalize output file");
        fs::rename(temporary, path);
    } catch (...) {
        std::error_code ignored;
        fs::remove(temporary, ignored);
        throw;
    }
}

uint64_t parse_timeout(const std::string& text) {
    size_t consumed = 0;
    const auto timeout = std::stoull(text, &consumed);
    require(consumed == text.size() && timeout >= 1000 && timeout <= 3600000,
            "timeout must be 1000..3600000 milliseconds");
    return timeout;
}
#endif

#ifndef CKKSMAC_PARSER_ONLY

std::chrono::milliseconds remaining_time(
    const std::chrono::steady_clock::time_point& deadline) {
    const auto now = std::chrono::steady_clock::now();
    require(now < deadline, "hardware execution timeout");
    auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - now);
    if (remaining.count() == 0)
        remaining = std::chrono::milliseconds(1);
    return remaining;
}

void wait_for_run(const char* name, xrt::run& run,
                  const std::chrono::steady_clock::time_point& deadline) {
    const auto state = run.wait(remaining_time(deadline));
    require(state != ERT_CMD_STATE_TIMEOUT,
            std::string(name) + " timed out");
    require(state == ERT_CMD_STATE_COMPLETED,
            std::string(name) + " ended in XRT state " +
                std::to_string(static_cast<unsigned>(state)));
}

void run_hardware(const fs::path& xclbin, const InputCase& input,
                  const fs::path& output_path, uint64_t timeout_ms) {
    using Clock = std::chrono::steady_clock;
    const auto path_begin = Clock::now();
    validate_boot_xclbin(xclbin);
    validate_boot_marker();
    // Hardware was programmed by PLM before Linux. Only register metadata.
    xrt::ini::set("Runtime.enable_flat", "false");
    xrt::ini::set("Runtime.force_program_xclbin", "false");
    xrt::ini::set("Runtime.ert_polling", "true");
    xrt::ini::set("Runtime.xgq_polling", "true");
    std::cout << "STAGE metadata registration begin (hardware already programmed at boot)\n"
              << std::flush;
    auto device = xrt::device(0);
    const auto uuid = device.load_xclbin(xclbin.string());
    std::cout << "STAGE metadata registration complete\n" << std::flush;

    auto reader = xrt::kernel(device, uuid, "ct_reader:{ct_reader_1}",
                              xrt::kernel::cu_access_mode::exclusive);
    auto reducer = xrt::kernel(device, uuid, "ct_reduce_accum:{ct_reduce_accum_1}",
                               xrt::kernel::cu_access_mode::exclusive);
    auto graph = xrt::graph(device, uuid, "ckks_graph");
    std::cout << "STAGE kernels_and_graph ready\n" << std::flush;
    const auto init_end = Clock::now();

    const auto parameters = pack_parameters(input);
    std::vector<uint64_t> output(static_cast<size_t>(input.output_words()), 0);
    const size_t input_bytes = input.words.size() * sizeof(uint64_t);
    const size_t parameter_bytes = parameters.size() * sizeof(uint64_t);
    const size_t output_bytes = output.size() * sizeof(uint64_t);

    auto input_bo = xrt::bo(device, input_bytes, reader.group_id(0));
    // Stream argument 0 is linked in hardware, so outputs and params retain
    // their original HLS argument indices 1 and 2.
    auto output_bo = xrt::bo(device, output_bytes, reducer.group_id(1));
    auto parameter_bo = xrt::bo(device, parameter_bytes, reducer.group_id(2));
    input_bo.write(input.words.data(), input_bytes, 0);
    parameter_bo.write(parameters.data(), parameter_bytes, 0);
    output_bo.write(output.data(), output_bytes, 0);
    input_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    parameter_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    output_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    const auto upload_end = Clock::now();

    xrt::run reducer_run(reducer);
    reducer_run.set_arg(1, output_bo);
    reducer_run.set_arg(2, parameter_bo);
    reducer_run.set_arg(3, input.n);
    reducer_run.set_arg(4, input.l);
    reducer_run.set_arg(5, input.k);

    xrt::run reader_run(reader);
    reader_run.set_arg(0, input_bo);
    // Arguments 1 and 2 are hardware-connected AXI streams.
    reader_run.set_arg(3, input.n);
    reader_run.set_arg(4, input.l);
    reader_run.set_arg(5, input.k);

    const uint64_t frame_count = input.frames();
    require(frame_count <= static_cast<uint64_t>(std::numeric_limits<int>::max()),
            "AIE frame count exceeds graph API range");
    graph.reset();
    std::cout << "STAGE execution begin frames=" << frame_count << "\n" << std::flush;
    const auto execution_begin = Clock::now();
    reducer_run.start();
    graph.run(static_cast<int>(frame_count));
    reader_run.start();

    const auto deadline = std::chrono::steady_clock::now() +
                          std::chrono::milliseconds(timeout_ms);
    try {
        wait_for_run("ct_reader", reader_run, deadline);
        wait_for_run("ct_reduce_accum", reducer_run, deadline);
        graph.wait(remaining_time(deadline));
    } catch (...) {
        try { reader_run.abort(); } catch (...) {}
        try { reducer_run.abort(); } catch (...) {}
        try { graph.reset(); } catch (...) {}
        throw;
    }
    const auto execution_end = Clock::now();

    // Both kernels return only values validated by the host before launch.
    // Reading 0x10 verifies the HLS ap_return register itself.
    const uint32_t reader_status = reader.read_register(0x10);
    const uint32_t reducer_status = reducer.read_register(0x10);
    require(reader_status == 0, "ct_reader ap_return=" + std::to_string(reader_status));
    require(reducer_status == 0,
            "ct_reduce_accum ap_return=" + std::to_string(reducer_status));

    output_bo.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
    output_bo.read(output.data(), output_bytes, 0);
    const auto readback_end = Clock::now();
    for (size_t index = 0; index < output.size(); ++index) {
        const uint32_t tower = static_cast<uint32_t>(index / (uint64_t(input.n) * 3));
        require(output[index] < input.parameters[tower].q,
                "noncanonical hardware output at word " + std::to_string(index));
    }
    const auto validation_end = Clock::now();
    write_output(output_path, input, output);

    const auto ms = [](auto begin, auto end) {
        return std::chrono::duration<double, std::milli>(end - begin).count();
    };
    // Host wall times. Execution includes launch, PL DDR traffic and waiting;
    // it is not an isolated AIE kernel cycle count. File I/O is excluded.
    std::cout << std::fixed << std::setprecision(6)
              << "TIMING init_ms=" << ms(path_begin, init_end)
              << " upload_ms=" << ms(init_end, upload_end)
              << " setup_ms=" << ms(upload_end, execution_begin)
              << " execution_ms=" << ms(execution_begin, execution_end)
              << " readback_ms=" << ms(execution_end, readback_end)
              << " validation_ms=" << ms(readback_end, validation_end)
              << " host_path_ms=" << ms(path_begin, validation_end) << "\n";

    std::cout << "PASS hardware frames=" << frame_count << " N=" << input.n
              << " L=" << input.l << " K=" << input.k
              << " output_words=" << output.size() << "\n"
              << "OUTPUT_RESULT=\"" << output_path.string() << "\"\n";
}

#endif

void print_inspection(const InputCase& input) {
    const auto parameters = pack_parameters(input);
    std::cout << "PASS input N=" << input.n << " L=" << input.l << " K=" << input.k
              << " input_words=" << input.words.size()
              << " parameter_bytes=" << parameters.size() * sizeof(uint64_t)
              << " frames=" << input.frames()
              << " output_words=" << input.output_words() << "\n";
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 3 && std::string(argv[1]) == "--inspect-xclbin") {
            validate_boot_xclbin(argv[2]);
            return 0;
        }
#ifdef CKKSMAC_PARSER_ONLY
        if (argc != 2) {
            std::cerr << "Usage: ckks_mac_parser INPUT_BIN\n";
            return 2;
        }
        print_inspection(read_input(argv[1]));
#else
        if (argc < 4 || argc > 5) {
            std::cerr << "Usage: ckks_mac_boot_xrt XCLBIN INPUT_BIN OUTPUT_BIN [TIMEOUT_MS]\n";
            return 2;
        }
        const uint64_t timeout_ms = argc == 5 ? parse_timeout(argv[4]) : 120000;
        const auto input = read_input(argv[2]);
        print_inspection(input);
        run_hardware(argv[1], input, argv[3], timeout_ms);
#endif
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << "\n";
        return 1;
    }
}
