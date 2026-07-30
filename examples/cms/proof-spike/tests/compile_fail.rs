//! Compile-fail regression test for the `authz::Grant<Op>` boundary
//! (research/09-bridging-the-gap.md, Track D's "boundary problem").
//!
//! Each file under `tests/compile-fail/` is a program that a caller might
//! plausibly write if they were trying to bypass the kernel; every one of
//! them must fail to compile. No `.stderr` snapshot is checked in on
//! purpose -- the exact `rustc` wording drifts across compiler versions,
//! and "fails to compile" is the actual guarantee we're pinning down here,
//! not a specific diagnostic string. The real compiler output, captured on
//! this run, is quoted verbatim in `proof-spike/README.md`.
#[test]
fn boundary_violations_do_not_compile() {
    let t = trybuild::TestCases::new();
    t.compile_fail("tests/compile-fail/*.rs");
}
