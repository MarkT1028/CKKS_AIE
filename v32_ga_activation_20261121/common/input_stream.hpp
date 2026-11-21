#pragma once

#include <arpa/inet.h>
#include <cerrno>
#include <cstdlib>
#include <initializer_list>
#include <netinet/tcp.h>
#include <stdexcept>
#include <string>
#include <sys/socket.h>
#include <unistd.h>

namespace ga_stream {

inline bool enabled() {
    const char* address = std::getenv("V32_GA_INPUT_IP");
    return address && *address;
}

struct Buffer { void* data; size_t size; };

class Connection {
    int fd = -1;

    void close_socket() noexcept {
        if (fd >= 0) ::close(fd);
        fd = -1;
    }

    void send_line(const std::string& line) const {
        size_t offset = 0;
        while (offset < line.size()) {
            const auto count = ::send(fd, line.data() + offset, line.size() - offset, MSG_NOSIGNAL);
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) throw std::runtime_error("GA input stream send failed");
            offset += size_t(count);
        }
    }

    void receive(Buffer dest) const {
        size_t offset = 0;
        auto* data = static_cast<char*>(dest.data);
        while (offset < dest.size) {
            const auto count = ::recv(fd, data + offset, dest.size - offset, 0);
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) throw std::runtime_error("GA input stream interrupted or truncated");
            offset += size_t(count);
        }
    }

    void expect_ready(const std::string& message) const {
        char reply = 0;
        receive({&reply, 1});
        if (reply != 'Y') throw std::runtime_error(message);
    }

    void open_socket() {
        const char* port_text = std::getenv("V32_GA_INPUT_PORT");
        const char* key_text = std::getenv("V32_GA_INPUT_KEY");
        const std::string port = port_text && *port_text ? port_text : "8407";
        const std::string key = key_text ? key_text : "";
        sockaddr_in endpoint{};
        endpoint.sin_family = AF_INET;
        if (port.empty() || port.size() > 5 || port.find_first_not_of("0123456789") != std::string::npos
            || std::stoul(port) == 0 || std::stoul(port) > 65535 || key.size() != 64
            || key.find_first_not_of("0123456789abcdef") != std::string::npos
            || ::inet_pton(AF_INET, std::getenv("V32_GA_INPUT_IP"), &endpoint.sin_addr) != 1)
            throw std::runtime_error("invalid GA input stream IP, port or 64-character key");
        endpoint.sin_port = htons(uint16_t(std::stoul(port)));
        fd = ::socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
        if (fd < 0) throw std::runtime_error("cannot create GA input stream socket");
        const timeval timeout{30, 0};
        const int yes = 1;
        if (::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) != 0
            || ::setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) != 0
            || ::setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof(yes)) != 0
            || ::connect(fd, reinterpret_cast<sockaddr*>(&endpoint), sizeof(endpoint)) != 0)
            throw std::runtime_error("cannot connect to GA input sender");
        send_line("V32GA1 " + key + "\n");
        expect_ready("GA input sender rejected the connection");
    }

public:
    Connection() = default;
    ~Connection() { close_socket(); }
    Connection(const Connection&) = delete;
    Connection& operator=(const Connection&) = delete;

    void fetch(const std::string& layer, const std::string& file, std::initializer_list<Buffer> outputs) {
        if (file.empty() || file.size() > 192 || file[0] == '/' || file.find("..") != std::string::npos
            || file.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./-") != std::string::npos)
            throw std::runtime_error("invalid sealed GA input path");
        size_t bytes = 0;
        for (const auto& output : outputs) bytes += output.size;
        if (bytes == 0 || bytes > 64*1024*1024) throw std::runtime_error("invalid GA streamed input size");
        try {
            if (fd < 0) open_socket();
            send_line(layer + " " + file + " " + std::to_string(bytes) + "\n");
            expect_ready("GA input sender rejected " + layer + "/" + file);
            for (auto output : outputs) receive(output);
        } catch (...) {
            close_socket();
            throw;
        }
    }
};

inline void fetch(const std::string& layer, const std::string& file, std::initializer_list<Buffer> outputs) {
    // A read-ahead worker and its consumer can each own a stream.
    thread_local Connection connection;
    connection.fetch(layer, file, outputs);
}

}
