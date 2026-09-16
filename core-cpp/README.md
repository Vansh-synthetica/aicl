# AICL C++ Model Adapter

**Purpose**: Native AI/model/hardware integration layer. Bridges the Rust AICL runtime to model inference backends.

**Design constraints**:
- No HTTP, REST, `/v1`, or localhost
- No duplication of the Rust AICL protocol core
- Zero-copy buffer passing where possible

## Architecture

```
AICL Instruction (Rust)
       ↓
   Rust Runtime (core-rust)
       ↓ (FFI via aicl_model.h)
   C++ Model Adapter (core-cpp)
       ↓
   Backend: Dummy / Llama.cpp (native-cpp)
       ↓
   GGUF Model / CPU / GPU
```

## Concepts

| Concept | Purpose |
|---------|---------|
| `ModelContext` | Owns BufferRegistry + model registry |
| `IModel` | Per-model inference interface |
| `ModelRequest` | Input: target cap, inputs, buffers, flags |
| `ModelResponse` | Output: text, tensors, error info |
| `BufferRef` | Zero-copy 16-byte buffer descriptor |
| `CapRef` | u16 model registry index |

## Building

```bash
# C++20 required
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build

# With llama.cpp support (requires llama.cpp source)
cmake -B build -DCMAKE_BUILD_TYPE=Release \
  -DAICL_WITH_LLAMA=ON \
  -DAICL_LLAMA_PATH=/path/to/llama.cpp
cmake --build build
```

## Running the Demo

```bash
./build/examples/aicl_demo
```

Expected output shows:
- Model registration with capability ref
- Non-streaming inference call
- Streaming inference with token-by-token output
- Resource usage reporting
- Zero-copy buffer registry

## Testing

```bash
ctest --output-on-failure
```

## Files

```
core-cpp/
├── include/
│   ├── aicl_model.h              # C ABI header (for Rust FFI)
│   └── aicl/
│       ├── aicl_adapter.hpp      # Top-level bridge
│       ├── aicl_context.hpp       # Model context + registry
│       ├── aicl_model.hpp         # IModel interface
│       ├── aicl_session.hpp       # Per-call session
│       ├── aicl_value.hpp         # Tagged union (Value/Operand)
│       ├── aicl_buffer.hpp        # BufferRegistry
│       ├── aicl_backend.hpp       # Backend factory
│       └── aicl_tensor.hpp        # Tensor/embedding types
├── src/
│   ├── aicl_adapter.cpp           # Adapter implementation
│   ├── aicl_model.cpp             # Dummy backend + factory
│   └── ...
├── csrc/
│   └── aicl_model_c.cpp           # C ABI shim
└── examples/
    └── aicl_demo.cpp              # End-to-end demo

native-cpp/
├── include/
│   └── llama_backend.hpp          # llama.cpp wrapper
├── src/
│   └── llama_backend.cpp         # LlamaModel implementation
└── CMakeLists.txt
```

## Buffer Copy Semantics

| Type | Copy Behavior |
|------|--------------|
| `Value::Str` | Deep copy on Value copy |
| `Value::Bytes` | Reference-counted via `shared_ptr` |
| `Value::Tensor` | Shares data via `BufferRef` |
| `BufferRef` | 16-byte descriptor (passed by value, points to shared buffer) |
| `ModelRequest.input_buffers` | Zero-copy reference |

## C API Usage (from Rust)

```rust
use std::ffi::CString;

// Create adapter
let mut adapter: *mut aicl_adapter_t = std::ptr::null_mut();
aicl_adapter_create(&mut adapter);

// Register model
let mut cap: u16 = 0;
let name = CString::new("my-model").unwrap();
aicl_adapter_register_model(adapter, name.as_ptr(), std::ptr::null(), &mut cap);

// Make inference call
let call = aicl_call_t { /* ... */ };
let mut out = aicl_call_t { /* ... */ };
aicl_adapter_handle_call(adapter, &call, &mut out);

// Cleanup
aicl_adapter_destroy(adapter);
```
