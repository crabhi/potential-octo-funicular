// P3 conformance harness — toy API.
//
// Domain: `users` table with columns `id` (PK) and `name` (text). A schema
// migration (see ../migrate/migrate.py) renames `name` to `full_name` via
// expand/contract. This binary can run as either APP_VERSION=1 (old code,
// only knows about `name`) or APP_VERSION=2 (new code, aware of the
// migration and able to dual-write / switch reads based on the
// `migration_state` table). Two instances of this binary (one per version)
// run concurrently to simulate version skew during a rollout, exactly the
// scenario research/05-db-migrations-concurrency.md formalizes.
use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio_postgres::{Client, NoTls};

#[derive(Clone)]
struct AppState {
    client: Arc<Client>,
    version: u8,
}

#[derive(Deserialize)]
struct CreateUser {
    name: String,
}

#[derive(Deserialize)]
struct UpdateUser {
    name: String,
}

#[derive(Serialize)]
struct UserResp {
    id: i32,
    name: String,
}

#[derive(Serialize)]
struct ErrorResp {
    error: String,
}

/// Snapshot of `migration_state`, re-read on every request (toy-simple; a
/// real system would cache with a short TTL or push updates). Columns:
/// - dual_write: v2 should write both `name` and `full_name`.
/// - read_switch: it is safe to read `full_name` as the source of truth.
/// - contracted: `name` has been dropped; only `full_name` exists.
struct MigrationFlags {
    dual_write: bool,
    read_switch: bool,
    contracted: bool,
}

async fn migration_flags(client: &Client) -> Result<MigrationFlags, tokio_postgres::Error> {
    let row = client
        .query_opt(
            "SELECT dual_write, read_switch, contracted FROM migration_state WHERE id = 1",
            &[],
        )
        .await?;
    Ok(match row {
        Some(r) => MigrationFlags {
            dual_write: r.get(0),
            read_switch: r.get(1),
            contracted: r.get(2),
        },
        None => MigrationFlags {
            dual_write: false,
            read_switch: false,
            contracted: false,
        },
    })
}

fn pg_err(e: tokio_postgres::Error) -> Response {
    // Surface the raw Postgres error text so the harness can distinguish
    // "column does not exist" (a schema/version-skew bug) from any other
    // failure. tokio-postgres's Display impl for Error is a terse summary
    // ("db error"); the detailed message lives on the underlying DbError.
    let msg = e
        .as_db_error()
        .map(|dbe| dbe.message().to_string())
        .unwrap_or_else(|| e.to_string());
    (StatusCode::INTERNAL_SERVER_ERROR, Json(ErrorResp { error: msg })).into_response()
}

async fn health() -> &'static str {
    "ok"
}

async fn create_user(State(state): State<AppState>, Json(body): Json<CreateUser>) -> Response {
    let client = &*state.client;
    if state.version == 1 {
        return match client
            .query_one("INSERT INTO users (name) VALUES ($1) RETURNING id", &[&body.name])
            .await
        {
            Ok(row) => {
                let id: i32 = row.get(0);
                (StatusCode::CREATED, Json(UserResp { id, name: body.name })).into_response()
            }
            Err(e) => pg_err(e),
        };
    }

    // version == 2
    let flags = match migration_flags(client).await {
        Ok(f) => f,
        Err(e) => return pg_err(e),
    };
    let query = if flags.contracted {
        "INSERT INTO users (full_name) VALUES ($1) RETURNING id"
    } else if flags.dual_write {
        "INSERT INTO users (name, full_name) VALUES ($1, $1) RETURNING id"
    } else {
        "INSERT INTO users (name) VALUES ($1) RETURNING id"
    };
    match client.query_one(query, &[&body.name]).await {
        Ok(row) => {
            let id: i32 = row.get(0);
            (StatusCode::CREATED, Json(UserResp { id, name: body.name })).into_response()
        }
        Err(e) => pg_err(e),
    }
}

async fn get_user(State(state): State<AppState>, Path(id): Path<i32>) -> Response {
    let client = &*state.client;
    let query = if state.version == 1 {
        "SELECT name FROM users WHERE id = $1"
    } else {
        let flags = match migration_flags(client).await {
            Ok(f) => f,
            Err(e) => return pg_err(e),
        };
        if flags.contracted {
            "SELECT full_name FROM users WHERE id = $1"
        } else if flags.read_switch {
            // Defensive COALESCE: by construction (see migrate.py) full_name
            // is never null once the trigger is installed, but this keeps
            // the read path robust if that invariant were ever violated.
            "SELECT COALESCE(full_name, name) FROM users WHERE id = $1"
        } else {
            "SELECT name FROM users WHERE id = $1"
        }
    };
    match client.query_opt(query, &[&id]).await {
        Ok(Some(row)) => {
            let name: String = row.get(0);
            (StatusCode::OK, Json(UserResp { id, name })).into_response()
        }
        Ok(None) => (
            StatusCode::NOT_FOUND,
            Json(ErrorResp { error: "not found".into() }),
        )
            .into_response(),
        Err(e) => pg_err(e),
    }
}

async fn update_user(
    State(state): State<AppState>,
    Path(id): Path<i32>,
    Json(body): Json<UpdateUser>,
) -> Response {
    let client = &*state.client;
    if state.version == 1 {
        return match client
            .execute("UPDATE users SET name = $1 WHERE id = $2", &[&body.name, &id])
            .await
        {
            Ok(0) => (
                StatusCode::NOT_FOUND,
                Json(ErrorResp { error: "not found".into() }),
            )
                .into_response(),
            Ok(_) => (StatusCode::OK, Json(UserResp { id, name: body.name })).into_response(),
            Err(e) => pg_err(e),
        };
    }

    let flags = match migration_flags(client).await {
        Ok(f) => f,
        Err(e) => return pg_err(e),
    };
    let query = if flags.contracted {
        "UPDATE users SET full_name = $1 WHERE id = $2"
    } else if flags.dual_write {
        "UPDATE users SET name = $1, full_name = $1 WHERE id = $2"
    } else {
        "UPDATE users SET name = $1 WHERE id = $2"
    };
    match client.execute(query, &[&body.name, &id]).await {
        Ok(0) => (
            StatusCode::NOT_FOUND,
            Json(ErrorResp { error: "not found".into() }),
        )
            .into_response(),
        Ok(_) => (StatusCode::OK, Json(UserResp { id, name: body.name })).into_response(),
        Err(e) => pg_err(e),
    }
}

#[tokio::main]
async fn main() {
    let version: u8 = std::env::var("APP_VERSION")
        .unwrap_or_else(|_| "1".into())
        .parse()
        .expect("APP_VERSION must be 1 or 2");
    let port: u16 = std::env::var("PORT")
        .unwrap_or_else(|_| "3001".into())
        .parse()
        .expect("PORT must be a number");
    let db_url = std::env::var("DATABASE_URL")
        .unwrap_or_else(|_| "host=127.0.0.1 user=root password=p3demo dbname=p3demo".into());

    let (client, connection) = tokio_postgres::connect(&db_url, NoTls)
        .await
        .expect("failed to connect to postgres");
    tokio::spawn(async move {
        if let Err(e) = connection.await {
            eprintln!("postgres connection error: {e}");
        }
    });

    let state = AppState {
        client: Arc::new(client),
        version,
    };

    let app = Router::new()
        .route("/health", get(health))
        .route("/users", post(create_user))
        .route("/users/:id", get(get_user).put(update_user))
        .with_state(state);

    let addr = format!("0.0.0.0:{port}");
    let listener = tokio::net::TcpListener::bind(&addr).await.expect("bind");
    eprintln!("p3_api v{version} listening on {addr}");
    axum::serve(listener, app).await.expect("serve");
}
