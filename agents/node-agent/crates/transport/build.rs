//! Generates the `netsvcs.manager.v1` gRPC client stubs from the shared
//! proto contract at build time, using a vendored `protoc` binary
//! (`protoc-bin-vendored`) so the workspace never depends on a
//! system-installed Protocol Buffers compiler.

use std::path::PathBuf;

fn main() -> std::io::Result<()> {
    let protoc = protoc_bin_vendored::protoc_bin_path()
        .expect("protoc-bin-vendored must ship a protoc binary for this host platform");
    // SAFETY: build scripts are single-threaded at this point in Cargo's
    // invocation, so there is no concurrent access to the process environment.
    unsafe {
        std::env::set_var("PROTOC", protoc);
    }

    // Anchor to CARGO_MANIFEST_DIR (always this crate's own directory) rather
    // than a hardcoded relative-`..` count, which is fragile to workspace
    // nesting changes.
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let proto_root = manifest_dir.join("../../../../proto");
    let proto_file = proto_root.join("netsvcs/v1/manager.proto");

    println!("cargo:rerun-if-changed={}", proto_file.display());

    // Server stubs are generated alongside the client purely for this
    // crate's own tests (an in-process mock `ManagerService` exercising
    // `GrpcClient` end-to-end over a real loopback gRPC connection) — the
    // `node-agent` binary never serves gRPC, only calls it, so
    // `ManagerServiceServer` stays unreferenced by any non-test code path.
    tonic_prost_build::configure()
        .build_server(true)
        .build_client(true)
        .compile_protos(&[proto_file], &[proto_root])
}
