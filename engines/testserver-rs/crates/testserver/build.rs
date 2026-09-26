//! Generates the `testserver.v1` gRPC server (+ client, for in-process
//! tests) stubs from the shared proto contract at build time, using a
//! vendored `protoc` binary (`protoc-bin-vendored`) so the workspace never
//! depends on a system-installed Protocol Buffers compiler. Mirrors
//! `agents/node-agent/crates/transport/build.rs`.

use std::path::PathBuf;

fn main() -> std::io::Result<()> {
    let protoc = protoc_bin_vendored::protoc_bin_path()
        .expect("protoc-bin-vendored must ship a protoc binary for this host platform");
    // SAFETY: build scripts are single-threaded at this point in Cargo's
    // invocation, so there is no concurrent access to the process environment.
    unsafe {
        std::env::set_var("PROTOC", protoc);
    }

    // Anchor to CARGO_MANIFEST_DIR (always this crate's own directory)
    // rather than a hardcoded relative-`..` count fragile to workspace
    // nesting changes.
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let proto_root = manifest_dir.join("../../../../proto");
    let proto_file = proto_root.join("testserver/v1/testserver.proto");

    println!("cargo:rerun-if-changed={}", proto_file.display());

    tonic_prost_build::configure()
        .build_server(true)
        .build_client(true)
        .compile_protos(&[proto_file], &[proto_root])
}
