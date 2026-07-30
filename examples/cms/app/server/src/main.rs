// Demo CMS server enforcing the invariants in
// examples/cms/invariants/cms-security.yaml against a running HTTP API.
//
// State is in-memory behind a tokio RwLock. No database — this is the
// "real system" rung of a worked example whose formal analysis lives in
// the sibling Quint model (../model/cms.qnt).
//
// The AUTH_MODE knob:
//   AUTH_MODE=cached (default) - the session token captures role+active at
//     login time; every later request trusts that snapshot. This is the
//     realistic "stale JWT" design, and it corresponds to setting the
//     formal model's CHECK_AT_ACTION constant to false (checked once, at
//     session-issue time).
//   AUTH_MODE=live - every request re-reads the acting user's current
//     role/active flag from the shared state before deciding.  This
//     corresponds to CHECK_AT_ACTION = true.
//
// Every authorization denial returns 403 with a JSON body naming the
// invariant it would otherwise violate, e.g. {"error": "inv_draft_visibility"}.
// That name is the machine-readable counterexample hook the Python harness
// asserts against.

use authz_spike::authz;
use authz_spike::{ArticleState, Role};
use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::Mutex;

// `Role` and `ArticleState` used to be hand-rolled here (identical shape to
// the kernel's copies purely by discipline, not by construction). They now
// come straight from the verified kernel crate (`authz_spike`, aka
// `examples/cms/proof-spike`) -- one less place for the two to drift, and
// the type the app's handlers are checked against is *the same type* the
// kernel's `authorize()`/Kani proofs were run against, not a look-alike.

#[derive(Clone, Debug, Serialize, Deserialize)]
struct User {
    name: String,
    role: Role,
    active: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct Article {
    id: u64,
    author: String,
    state: ArticleState,
    title: String,
    body: String,
}

// A session token. In `cached` mode, `role`/`active` are the values
// captured at login and never refreshed. In `live` mode they exist for
// bookkeeping but every handler re-reads `users` by `user` instead of
// trusting them.
#[derive(Clone, Debug, Serialize, Deserialize)]
struct Session {
    user: String,
    role: Role,
    active: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum AuthMode {
    Cached,
    Live,
}

struct AppState {
    users: HashMap<String, User>,
    articles: HashMap<u64, Article>,
    sessions: HashMap<String, Session>,
    next_article_id: u64,
    mode: AuthMode,
}

type SharedState = Arc<Mutex<AppState>>;

fn seed_state(mode: AuthMode) -> AppState {
    let mut users = HashMap::new();
    users.insert(
        "alice".to_string(),
        User { name: "alice".into(), role: Role::Author, active: true },
    );
    users.insert(
        "bob".to_string(),
        User { name: "bob".into(), role: Role::Author, active: true },
    );
    users.insert(
        "eve".to_string(),
        User { name: "eve".into(), role: Role::Editor, active: true },
    );
    users.insert(
        "root".to_string(),
        User { name: "root".into(), role: Role::Admin, active: true },
    );

    let mut articles = HashMap::new();
    articles.insert(
        1,
        Article {
            id: 1,
            author: "alice".into(),
            state: ArticleState::Published,
            title: "Published piece".into(),
            body: "everyone can read this".into(),
        },
    );
    articles.insert(
        2,
        Article {
            id: 2,
            author: "alice".into(),
            state: ArticleState::Draft,
            title: "Alice's draft".into(),
            body: "not public yet".into(),
        },
    );
    articles.insert(
        3,
        Article {
            id: 3,
            author: "bob".into(),
            state: ArticleState::InReview,
            title: "Bob's in-review piece".into(),
            body: "awaiting an editor".into(),
        },
    );
    articles.insert(
        4,
        Article {
            id: 4,
            author: "bob".into(),
            state: ArticleState::Archived,
            title: "Old archived piece".into(),
            body: "staff reference only".into(),
        },
    );

    AppState { users, articles, sessions: HashMap::new(), next_article_id: 5, mode }
}

// ---- error / denial helpers -------------------------------------------------

struct Denied(&'static str);

impl IntoResponse for Denied {
    fn into_response(self) -> Response {
        (StatusCode::FORBIDDEN, Json(serde_json::json!({ "error": self.0 }))).into_response()
    }
}

struct NotFound;
impl IntoResponse for NotFound {
    fn into_response(self) -> Response {
        (StatusCode::NOT_FOUND, Json(serde_json::json!({ "error": "not_found" }))).into_response()
    }
}

enum ApiError {
    Denied(&'static str),
    NotFound,
}
impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        match self {
            ApiError::Denied(r) => Denied(r).into_response(),
            ApiError::NotFound => NotFound.into_response(),
        }
    }
}

// Resolve the *acting* role/active flag for a session token according to
// AUTH_MODE. This is the one function that embodies the knob: cached mode
// trusts the token; live mode re-reads current user state.
fn resolve_identity(state: &AppState, token: &str) -> Option<(String, Role, bool)> {
    let session = state.sessions.get(token)?;
    match state.mode {
        AuthMode::Cached => Some((session.user.clone(), session.role, session.active)),
        AuthMode::Live => {
            let user = state.users.get(&session.user)?;
            Some((session.user.clone(), user.role, user.active))
        }
    }
}

// The acting principal for a request, folded to Anonymous when there's no
// token or the token doesn't resolve to a session. This -- along with
// `resolve_identity` above -- is identity-*resolution* code: it decides
// *which* snapshot of a user's role/active flag to trust (the AUTH_MODE
// knob), not *whether* that role/active/state combination is allowed to do
// anything. That second question is the kernel's (`authz::require`), not
// this function's. `boundary_lint.sh` does not scan this function -- it
// legitimately needs to name `Role::Anonymous` as the identity-resolution
// fallback.
struct ActingUser {
    user: Option<String>,
    role: Role,
    active: bool,
}

fn resolve_acting_user(state: &AppState, token: Option<&str>) -> ActingUser {
    match token.and_then(|t| resolve_identity(state, t)) {
        Some((user, role, active)) => ActingUser { user: Some(user), role, active },
        None => ActingUser { user: None, role: Role::Anonymous, active: true },
    }
}

// ---- request/response bodies ------------------------------------------------

#[derive(Deserialize)]
struct LoginReq {
    user: String,
}

#[derive(Serialize)]
struct LoginResp {
    token: String,
    user: String,
    role: Role,
}

#[derive(Deserialize)]
struct CreateArticleReq {
    title: String,
    body: String,
}

#[derive(Deserialize)]
struct EditArticleReq {
    title: Option<String>,
    body: Option<String>,
}

// Token is passed as `Authorization: Bearer <token>` or `?token=` query
// param for convenience with plain `requests.get`.
fn extract_token(headers: &axum::http::HeaderMap, query_token: Option<String>) -> Option<String> {
    if let Some(v) = headers.get("authorization") {
        if let Ok(s) = v.to_str() {
            if let Some(rest) = s.strip_prefix("Bearer ") {
                return Some(rest.to_string());
            }
        }
    }
    query_token
}

// ---- handlers ----------------------------------------------------------------

async fn health() -> &'static str {
    "ok"
}

async fn login(
    State(state): State<SharedState>,
    Json(req): Json<LoginReq>,
) -> Result<Json<LoginResp>, ApiError> {
    let mut st = state.lock().await;
    let user = st.users.get(&req.user).cloned().ok_or(ApiError::NotFound)?;
    let token = uuid::Uuid::new_v4().to_string();
    st.sessions.insert(
        token.clone(),
        Session { user: user.name.clone(), role: user.role, active: user.active },
    );
    Ok(Json(LoginResp { token, user: user.name, role: user.role }))
}

#[derive(Deserialize)]
struct TokenQuery {
    token: Option<String>,
}

// Every protected read/mutation below follows the same shape: resolve the
// acting identity, ask the kernel for a `Grant<Op>`, and only then touch
// the article. There is no `if role == ...` / `if state == ...` access
// check left in this file for these four handlers -- that logic now lives
// in `authz_spike::authz` (proof-spike/src/authz.rs), and the *only* way to
// get past the `?` is a `Grant<Op>` the kernel actually issued. See
// `app/boundary_lint.sh` and `proof-spike/README.md` "what is now
// impossible by construction".
async fn get_article(
    State(state): State<SharedState>,
    Path(id): Path<u64>,
    headers: axum::http::HeaderMap,
    axum::extract::Query(q): axum::extract::Query<TokenQuery>,
) -> Result<axum::response::Response, ApiError> {
    use axum::response::IntoResponse;
    let st = state.lock().await;
    let article = st.articles.get(&id).cloned().ok_or(ApiError::NotFound)?;

    let token = extract_token(&headers, q.token);
    let acting = resolve_acting_user(&st, token.as_deref());
    let is_author = acting.user.as_deref() == Some(article.author.as_str());

    let identity = authz::Identity { role: acting.role, is_author, active: acting.active };
    authz::require::<authz::View>(identity, authz::ArticleMeta { state: article.state })
        .map_err(|d| ApiError::Denied(d.rule_name()))?;

    // Content fingerprint for HTTP caching (ETag-style). NOTE: computed
    // while the state lock is held.
    let mut fp: u64 = 0xcbf29ce484222325;
    for _ in 0..300 {
        for b in article.body.bytes().chain(article.title.bytes()) {
            fp = (fp ^ b as u64).wrapping_mul(0x100000001b3);
        }
    }
    drop(st);
    let mut resp = Json(article).into_response();
    resp.headers_mut().insert(
        "x-content-fingerprint",
        axum::http::HeaderValue::from_str(&format!("{fp:016x}")).unwrap(),
    );
    Ok(resp)
}

async fn create_article(
    State(state): State<SharedState>,
    headers: axum::http::HeaderMap,
    Json(req): Json<CreateArticleReq>,
) -> Result<Json<Article>, ApiError> {
    let mut st = state.lock().await;
    let token = extract_token(&headers, None).ok_or(ApiError::Denied("inv_anonymous_never_author"))?;
    let (user, _role, active) =
        resolve_identity(&st, &token).ok_or(ApiError::Denied("inv_anonymous_never_author"))?;
    if !active {
        return Err(ApiError::Denied("inv_deactivated_does_nothing"));
    }
    let id = st.next_article_id;
    st.next_article_id += 1;
    let article = Article {
        id,
        author: user,
        state: ArticleState::Draft,
        title: req.title,
        body: req.body,
    };
    st.articles.insert(id, article.clone());
    Ok(Json(article))
}

async fn edit_article(
    State(state): State<SharedState>,
    Path(id): Path<u64>,
    headers: axum::http::HeaderMap,
    Json(req): Json<EditArticleReq>,
) -> Result<Json<Article>, ApiError> {
    let mut st = state.lock().await;
    let article = st.articles.get(&id).cloned().ok_or(ApiError::NotFound)?;

    let token = extract_token(&headers, None);
    let acting = resolve_acting_user(&st, token.as_deref());
    let is_author = acting.user.as_deref() == Some(article.author.as_str());

    let identity = authz::Identity { role: acting.role, is_author, active: acting.active };
    authz::require::<authz::Edit>(identity, authz::ArticleMeta { state: article.state })
        .map_err(|d| ApiError::Denied(d.rule_name()))?;

    let a = st.articles.get_mut(&id).unwrap();
    if let Some(t) = req.title {
        a.title = t;
    }
    if let Some(b) = req.body {
        a.body = b;
    }
    Ok(Json(a.clone()))
}

async fn submit_article(
    State(state): State<SharedState>,
    Path(id): Path<u64>,
    headers: axum::http::HeaderMap,
) -> Result<Json<Article>, ApiError> {
    let mut st = state.lock().await;
    let article = st.articles.get(&id).cloned().ok_or(ApiError::NotFound)?;

    let token = extract_token(&headers, None);
    let acting = resolve_acting_user(&st, token.as_deref());
    let is_author = acting.user.as_deref() == Some(article.author.as_str());

    let identity = authz::Identity { role: acting.role, is_author, active: acting.active };
    authz::require::<authz::Submit>(identity, authz::ArticleMeta { state: article.state })
        .map_err(|d| ApiError::Denied(d.rule_name()))?;

    let a = st.articles.get_mut(&id).unwrap();
    a.state = ArticleState::InReview;
    Ok(Json(a.clone()))
}

async fn publish_article(
    State(state): State<SharedState>,
    Path(id): Path<u64>,
    headers: axum::http::HeaderMap,
) -> Result<Json<Article>, ApiError> {
    let mut st = state.lock().await;
    let article = st.articles.get(&id).cloned().ok_or(ApiError::NotFound)?;

    let token = extract_token(&headers, None);
    let acting = resolve_acting_user(&st, token.as_deref());
    let is_author = acting.user.as_deref() == Some(article.author.as_str());

    let identity = authz::Identity { role: acting.role, is_author, active: acting.active };
    authz::require::<authz::Publish>(identity, authz::ArticleMeta { state: article.state })
        .map_err(|d| ApiError::Denied(d.rule_name()))?;

    let a = st.articles.get_mut(&id).unwrap();
    a.state = ArticleState::Published;
    Ok(Json(a.clone()))
}

async fn admin_deactivate(
    State(state): State<SharedState>,
    Path(target): Path<String>,
    headers: axum::http::HeaderMap,
) -> Result<Json<User>, ApiError> {
    let mut st = state.lock().await;
    let token = extract_token(&headers, None).ok_or(ApiError::Denied("inv_publish_staff_only"))?;
    let (_user, role, active) =
        resolve_identity(&st, &token).ok_or(ApiError::Denied("inv_publish_staff_only"))?;
    if !active || role != Role::Admin {
        return Err(ApiError::Denied("inv_publish_staff_only"));
    }
    let u = st.users.get_mut(&target).ok_or(ApiError::NotFound)?;
    u.active = false;
    // Note: existing sessions for `target` are *not* revoked here. In
    // `cached` mode that's exactly the point: the old token keeps the
    // stale `active: true` it captured at login. In `live` mode it makes
    // no difference because every request re-reads `users` directly.
    Ok(Json(u.clone()))
}

async fn admin_demote(
    State(state): State<SharedState>,
    Path(target): Path<String>,
    headers: axum::http::HeaderMap,
) -> Result<Json<User>, ApiError> {
    let mut st = state.lock().await;
    let token = extract_token(&headers, None).ok_or(ApiError::Denied("inv_publish_staff_only"))?;
    let (_user, role, active) =
        resolve_identity(&st, &token).ok_or(ApiError::Denied("inv_publish_staff_only"))?;
    if !active || role != Role::Admin {
        return Err(ApiError::Denied("inv_publish_staff_only"));
    }
    let u = st.users.get_mut(&target).ok_or(ApiError::NotFound)?;
    u.role = Role::Author;
    Ok(Json(u.clone()))
}

#[tokio::main]
async fn main() {
    let mode = match std::env::var("AUTH_MODE").unwrap_or_else(|_| "cached".to_string()).as_str() {
        "live" => AuthMode::Live,
        _ => AuthMode::Cached,
    };
    eprintln!("cms-server starting in AUTH_MODE={:?}", mode);

    let state: SharedState = Arc::new(Mutex::new(seed_state(mode)));

    let app = Router::new()
        .route("/health", get(health))
        .route("/login", post(login))
        .route("/articles", post(create_article))
        .route("/articles/:id", get(get_article).put(edit_article))
        .route("/articles/:id/submit", post(submit_article))
        .route("/articles/:id/publish", post(publish_article))
        .route("/admin/deactivate/:user", post(admin_deactivate))
        .route("/admin/demote/:user", post(admin_demote))
        .with_state(state);

    let addr = std::env::var("CMS_ADDR").unwrap_or_else(|_| "0.0.0.0:3100".to_string());
    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    eprintln!("cms-server listening on {}", addr);
    axum::serve(listener, app).await.unwrap();
}
