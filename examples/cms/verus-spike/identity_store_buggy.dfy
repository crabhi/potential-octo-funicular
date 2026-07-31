// identity_store_buggy.dfy
//
// A deliberately-seeded copy of identity_store.dfy, in the same style as
// examples/cms/dafny-authz/authz_buggy.dfy: the `ensures` clauses (the
// theorems) are IDENTICAL to the correct file. Only ResolveLive's body
// changed -- one line, one subtle bug:
//
//     the `active` bit is read from the SESSION's own snapshot
//     (s.sessions[token].2) instead of from the current `users` map entry.
//
// This is exactly the bug class AuthMode::Live exists to rule out in
// main.rs: `resolve_identity`'s Live arm (lines 188-191) re-reads
// `state.users.get(&session.user)` for BOTH role and active. A version
// that instead read `active` off the session snapshot would silently
// degrade Live mode into Cached-mode staleness for the activity flag
// while still looking like it "re-reads on every request" (it still reads
// `users` for `role`). That is precisely the seeded bug below.
//
// `dafny verify` on this file must be REJECTED, and must name the
// RevocationImmediate ensures clause it can no longer satisfy. See
// check.sh step 2 and README.md "Buggy variant is rejected".

module IdentityStoreBuggy {

  datatype Option<T> = None | Some(value: T)

  datatype Role = Anonymous | Author | Editor | Admin

  datatype Store = Store(
    users: map<string, (Role, bool)>,
    sessions: map<string, (string, Role, bool)>
  )

  predicate Valid(s: Store)
  {
    forall t :: t in s.sessions ==> s.sessions[t].0 in s.users
  }

  function Login(s: Store, token: string, user: string): (s': Store)
    requires user in s.users
    requires Valid(s)
    ensures Valid(s')
    ensures s'.users == s.users
    ensures s'.sessions == s.sessions[token := (user, s.users[user].0, s.users[user].1)]
  {
    Store(s.users, s.sessions[token := (user, s.users[user].0, s.users[user].1)])
  }

  function Deactivate(s: Store, user: string): (s': Store)
    requires user in s.users
    requires Valid(s)
    ensures Valid(s')
    ensures s'.sessions == s.sessions
    ensures s'.users == s.users[user := (s.users[user].0, false)]
  {
    Store(s.users[user := (s.users[user].0, false)], s.sessions)
  }

  function Demote(s: Store, user: string): (s': Store)
    requires user in s.users
    requires Valid(s)
    ensures Valid(s')
    ensures s'.sessions == s.sessions
    ensures s'.users == s.users[user := (Author, s.users[user].1)]
  {
    Store(s.users[user := (Author, s.users[user].1)], s.sessions)
  }

  // BUG: `active` comes from the session snapshot (`s.sessions[token].2`),
  // not from `s.users[u].1`. Compare to identity_store.dfy's ResolveLive,
  // which takes the whole pair `s.users[u]` from the CURRENT users map.
  // `role` is still (correctly) re-read from `users`, which is what makes
  // this bug subtle: it looks like a live re-read, but the activity flag
  // it returns is exactly the stale one AuthMode::Live was introduced to
  // avoid.
  function ResolveLive(s: Store, token: string): Option<(Role, bool)>
  {
    if token !in s.sessions then None
    else
      var u := s.sessions[token].0;
      if u !in s.users then None else Some((s.users[u].0, s.sessions[token].2))
  }

  function ResolveCached(s: Store, token: string): Option<(Role, bool)>
  {
    if token !in s.sessions then None
    else Some((s.sessions[token].1, s.sessions[token].2))
  }

  lemma FreshnessLive(s: Store, token: string)
    requires Valid(s)
    requires token in s.sessions
    ensures ResolveLive(s, token) == Some(s.users[s.sessions[token].0])
  {
  }

  // THIS is the lemma the seeded bug breaks: after deactivation, a session
  // token that predates the deactivation still carries the OLD `active ==
  // true` in its snapshot, so the buggy ResolveLive returns
  // Some((role, true)) instead of Some((role, false)). The verifier cannot
  // prove the ensures clause below and rejects this file.
  lemma RevocationImmediate(s: Store, user: string, token: string)
    requires Valid(s)
    requires user in s.users
    requires token in s.sessions
    requires s.sessions[token].0 == user
    ensures ResolveLive(Deactivate(s, user), token) == Some((s.users[user].0, false))
  {
  }

}
