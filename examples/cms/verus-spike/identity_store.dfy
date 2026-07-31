// identity_store.dfy
//
// Track L (research/10-proof-escalation.md, "Real Rust code proof beyond
// the pure kernel: session/identity state machine in the app").
//
// Route taken: Verus was the first choice (it type-checks against actual
// Rust source, closing the extraction-fidelity gap that a hand-written
// model like this one cannot). `curl -I` against the verus-lang GitHub
// releases page returned HTTP 403 through the outbound proxy -- release
// binaries are unreachable from this environment, and there is no
// package-manager path to a Rust verifier here either. See README.md
// "Route taken" for the full note. This file is the Dafny fallback: a
// faithful *model* of the mutable session/identity logic in
// examples/cms/app/server/src/main.rs, proved with the same dafny+z3
// toolchain as examples/cms/dafny-authz/ (see check.sh, mirroring that
// directory's check.sh invocation style).
//
// What this models, cited against main.rs:
//
//   users    : map<string, (Role, bool)>          <-> AppState.users:
//              HashMap<String, User> where User{role, active}  (main.rs
//              lines 44-49, 77-83)
//   sessions : map<string, (string, Role, bool)>  <-> AppState.sessions:
//              HashMap<String, Session> where Session{user, role, active}
//              is the snapshot captured at login time (main.rs lines
//              64-69, 77-83)
//
//   Login      <-> `login` handler, main.rs lines 262-274: inserts a
//                  session snapshotting the CURRENT users-map entry.
//   Deactivate <-> `admin_deactivate` handler, main.rs lines 418-437:
//                  flips users[target].active to false and, per the
//                  comment at lines 432-435, does NOT touch `sessions` --
//                  modeled here by Deactivate leaving `sessions` untouched.
//   Demote     <-> `admin_demote` handler, main.rs lines 439-454: sets
//                  users[target].role = Author, likewise leaving
//                  `sessions` untouched.
//   ResolveLive   <-> `resolve_identity`, main.rs lines 184-193,
//                  AuthMode::Live arm (line 188-191): re-reads
//                  `users[session.user]` on every call.
//   ResolveCached <-> same function, AuthMode::Cached arm (line 187):
//                  trusts the token's captured (role, active) forever.
//
// This module is a model, not the extracted axum code -- see README.md
// "Extraction-fidelity gap" for exactly what that means and what would
// close it.

module IdentityStore {

  datatype Option<T> = None | Some(value: T)

  // Mirrors the kernel's Role type (examples/cms/proof-spike,
  // examples/cms/dafny-authz/authz.dfy) so this model's Role is literally
  // the same shape `resolve_acting_user` produces for authz::Identity.
  datatype Role = Anonymous | Author | Editor | Admin

  // The store: current per-user (role, active) truth, and per-token
  // session snapshots (user, role-at-login, active-at-login).
  datatype Store = Store(
    users: map<string, (Role, bool)>,
    sessions: map<string, (string, Role, bool)>
  )

  // Invariant maintained by every transition below: a session always names
  // a user that still exists in `users`. main.rs never removes entries
  // from `users` (deactivate/demote only mutate fields in place), so this
  // holds for the real system too.
  predicate Valid(s: Store)
  {
    forall t :: t in s.sessions ==> s.sessions[t].0 in s.users
  }

  // --- state transitions ------------------------------------------------

  // main.rs lines 262-274. Precondition mirrors `.ok_or(ApiError::NotFound)`
  // on the users lookup (line 267): login only succeeds for an existing
  // user. The session snapshot is exactly the CURRENT (role, active) of
  // that user -- there is no staleness at the instant of login itself.
  function Login(s: Store, token: string, user: string): (s': Store)
    requires user in s.users
    requires Valid(s)
    ensures Valid(s')
    ensures s'.users == s.users
    ensures s'.sessions == s.sessions[token := (user, s.users[user].0, s.users[user].1)]
  {
    Store(s.users, s.sessions[token := (user, s.users[user].0, s.users[user].1)])
  }

  // main.rs lines 418-437. Precondition mirrors the `.ok_or(NotFound)` on
  // the target-user lookup (line 430). `sessions` is untouched, matching
  // the explicit comment at lines 432-435: "existing sessions for `target`
  // are *not* revoked here."
  function Deactivate(s: Store, user: string): (s': Store)
    requires user in s.users
    requires Valid(s)
    ensures Valid(s')
    ensures s'.sessions == s.sessions
    ensures s'.users == s.users[user := (s.users[user].0, false)]
  {
    Store(s.users[user := (s.users[user].0, false)], s.sessions)
  }

  // main.rs lines 439-454. Same shape as Deactivate: only `users[target]`
  // changes (role forced to Author), `sessions` untouched.
  function Demote(s: Store, user: string): (s': Store)
    requires user in s.users
    requires Valid(s)
    ensures Valid(s')
    ensures s'.sessions == s.sessions
    ensures s'.users == s.users[user := (Author, s.users[user].1)]
  {
    Store(s.users[user := (Author, s.users[user].1)], s.sessions)
  }

  // --- identity resolution (the AUTH_MODE knob) --------------------------

  // main.rs lines 184-193, AuthMode::Live arm: re-read `users` by the
  // session's `user` field on every call. Under Valid(s), the inner lookup
  // always succeeds -- see FreshnessLive below.
  function ResolveLive(s: Store, token: string): Option<(Role, bool)>
  {
    if token !in s.sessions then None
    else
      var u := s.sessions[token].0;
      if u !in s.users then None else Some(s.users[u])
  }

  // main.rs lines 184-193, AuthMode::Cached arm: trust the (role, active)
  // captured in the session at login time, forever.
  function ResolveCached(s: Store, token: string): Option<(Role, bool)>
  {
    if token !in s.sessions then None
    else Some((s.sessions[token].1, s.sessions[token].2))
  }

  // --- Theorem (a): freshness --------------------------------------------
  //
  // resolveLive's returned (role, active) always equals the CURRENT
  // users-map entry for the session's user -- for every reachable state,
  // not sampled ones. This is what makes AuthMode::Live's re-read
  // meaningful rather than accidental.
  lemma FreshnessLive(s: Store, token: string)
    requires Valid(s)
    requires token in s.sessions
    ensures ResolveLive(s, token) == Some(s.users[s.sessions[token].0])
  {
    // Follows directly from Valid(s) (the session's user is guaranteed to
    // be in `users`) and the definition of ResolveLive; no additional
    // strengthening needed -- Dafny discharges this by unfolding.
  }

  // --- Theorem (b): revocation immediacy under AuthMode::Live -----------
  //
  // After deactivating user `u`, ResolveLive on ANY session token
  // belonging to `u` (not a sampled one -- `token` is universally
  // quantified by being a lemma parameter under `requires`) returns
  // active == false. This is the code-level statement of what Track I's
  // cms_live invariant proved for the abstract model: live re-reads make
  // revocation take effect on the very next request.
  lemma RevocationImmediate(s: Store, user: string, token: string)
    requires Valid(s)
    requires user in s.users
    requires token in s.sessions
    requires s.sessions[token].0 == user
    ensures ResolveLive(Deactivate(s, user), token) == Some((s.users[user].0, false))
  {
  }

  // Same statement for the role field under Demote, for symmetry with (b)
  // and to cover main.rs's other users-map mutation (line 452).
  lemma DemotionImmediate(s: Store, user: string, token: string)
    requires Valid(s)
    requires user in s.users
    requires token in s.sessions
    requires s.sessions[token].0 == user
    ensures ResolveLive(Demote(s, user), token) == Some((Author, s.users[user].1))
  {
  }

  // --- Theorem (c): the live/cached asymmetry, as an existence proof -----
  //
  // This is the code-level twin of the abstract model's CHECK_AT_ACTION
  // CTI (research/10-proof-escalation.md episode log, Track I(b): "the
  // SAME invariant fails consecution on cms_cached with a concrete CTI
  // (cached EDITOR, demoted live role)"). Rather than searching for the
  // counterexample, this lemma CONSTRUCTS a concrete witness state and
  // machine-checks that it has the claimed shape: a deactivated editor
  // whose live identity is correctly revoked (active == false) while her
  // still-live session token's cached view says active == true. The
  // asymmetry is not "the tests happened not to catch it" -- it is proven
  // to exist as a reachable state, with a witness anyone can replay.
  lemma CachedStaleAfterDeactivation() returns (s: Store, token: string, user: string)
    ensures Valid(s)
    ensures user in s.users
    ensures token in s.sessions
    ensures s.sessions[token].0 == user
    ensures !s.users[user].1
    ensures ResolveLive(s, token) == Some((Editor, false))
    ensures ResolveCached(s, token) == Some((Editor, true))
  {
    var s0 := Store(map["eve" := (Editor, true)], map[]);
    var s1 := Login(s0, "tok-eve", "eve");
    var s2 := Deactivate(s1, "eve");
    s := s2;
    token := "tok-eve";
    user := "eve";
  }

}
