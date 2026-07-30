// A caller trying to bypass the kernel entirely: construct a `Grant`
// without ever calling `authz::require`. Must fail -- `_op` is a private
// field of `Grant`, and `Grant` is `#[non_exhaustive]` on top of that, so
// this crate (an external crate relative to `authz_spike::authz`) has no
// struct-literal syntax that can produce one.
use authz_spike::authz::{Grant, View};

fn main() {
    let _forged: Grant<View> = Grant {
        _op: std::marker::PhantomData,
    };
}
