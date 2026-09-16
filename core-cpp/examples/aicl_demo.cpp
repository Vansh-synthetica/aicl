// =============================================================================
//  aicl_demo.cpp — End-to-end AICL demonstration
//  -----------------------------------------------------------------------------
//  Demonstrates: AICL instruction -> C++ adapter -> Dummy model -> response
//
//  In production, the Rust core drives this via C ABI (aicl_model_c.c).
// =============================================================================
#include <aicl/aicl_adapter.hpp>
#include <aicl/aicl_model.hpp>
#include <aicl/aicl_value.hpp>

#include <chrono>
#include <iostream>
#include <iomanip>

using namespace aicl;

void print_sep(const std::string& title) {
    std::cout << "\n========== " << title << " ==========\n";
}

int main() {
    std::cout << "AICL C++ Model Adapter - End-to-End Demo\n";
    std::cout << "=========================================\n";

    AICLModelAdapter adapter;
    adapter.install_backend(BackendKind::Dummy, "", 2048);

    auto model = load_model(BackendKind::Dummy, "", {});
    if (!model) { std::cerr << "Failed to load model\n"; return 1; }
    model->info().id = "demo-model";
    model->info().family = "dummy";
    model->info().capabilities = {"text.generate", "text.embed"};

    u16 cap = adapter.register_model(std::move(model));
    std::cout << "Registered model with capability ref: " << cap << "\n";

    print_sep("Capability Advertisement");
    auto caps = adapter.advertised_capabilities();
    std::cout << "Advertised capabilities (" << caps.size() << "):\n";
    for (const auto& c : caps) std::cout << "  - " << c << "\n";

    print_sep("Non-Streaming Inference Call");
    Uuid corr_id{};
    for (int i = 0; i < 16; ++i) corr_id[i] = static_cast<u8>(i * 17);

    ModelRequest req;
    req.target = cap;
    req.correlation_id = corr_id;
    req.deadline_ms = 5000;
    req.flags = AiclFlags(AiclFlags::REQUEST);
    req.inputs["prompt"] = Value::from_string("Hello, AICL!");

    ModelResponse resp;
    auto t0 = std::chrono::steady_clock::now();
    adapter.handle_call(req, resp);
    auto t1 = std::chrono::steady_clock::now();
    double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

    std::cout << "Request: prompt=\"Hello, AICL!\", target cap=" << req.target << "\n";
    std::cout << "Response: error_code=" << resp.error_code << "\n";
    if (resp.error_code == 0) {
        std::cout << "  text: \"" << resp.outputs["text"].as_str() << "\"\n";
        std::cout << "  inference time: " << std::fixed << std::setprecision(2) << ms << " ms\n";
    } else {
        std::cout << "  error: " << resp.error_message << "\n";
    }

    print_sep("Streaming Inference Call");
    Uuid stream_id{};
    for (int i = 0; i < 16; ++i) stream_id[i] = static_cast<u8>(i * 19);

    ModelRequest sreq;
    sreq.target = cap;
    sreq.correlation_id = stream_id;
    sreq.deadline_ms = 5000;
    sreq.flags = AiclFlags(AiclFlags::REQUEST | AiclFlags::STREAM_CHUNK);
    sreq.inputs["prompt"] = Value::from_string("ABC");

    std::cout << "Streaming tokens:\n  ";
    int chunks = 0;
    adapter.handle_stream(sreq, [&](const ModelResponse& chunk) -> bool {
        if (chunk.flags.has(AiclFlags::STREAM_END)) {
            std::cout << "\n[STREAM_END]\n";
            return false;
        }
        if (chunk.outputs.count("token")) {
            std::cout << chunk.outputs["token"].as_str();
            chunks++;
        }
        return true;
    });
    std::cout << "Total chunks: " << chunks << "\n";

    print_sep("Resource Usage Report");
    ResourceUsage usage = adapter.report();
    std::cout << "Bytes loaded: " << usage.bytes_loaded << "\n";
    std::cout << "KV cache bytes: " << usage.kv_bytes << "\n";
    std::cout << "Last inference: " << usage.last_inference_ms << " ms\n";

    print_sep("Zero-Copy Buffer Registry");
    const char data[] = "AICL test payload";
    auto buf = std::make_shared<std::vector<u8>>(
        reinterpret_cast<const u8*>(data),
        reinterpret_cast<const u8*>(data) + sizeof(data));
    u64 buf_id = adapter.context().buffers().register_buffer(buf);
    std::cout << "Buffer id: " << buf_id << " (size=" << buf->size() << ")\n";
    const u8* retrieved = adapter.context().buffers().data(buf_id, 0, static_cast<u32>(buf->size()));
    if (retrieved) {
        std::cout << "Retrieved: \"" << retrieved << "\"\n";
    }

    adapter.shutdown();
    std::cout << "\n=== Demo completed successfully ===\n";
    return 0;
}