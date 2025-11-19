use axum::extract::State;
use log::info;

use crate::{
    api::{Blacklist, ClientMessage, QueryRequest, QueryResponse},
    qu, query, AppState,
};

pub async fn handle_query_items(
    State(state): State<AppState>,
    axum::Json(payload): axum::Json<QueryRequest>,
) -> (axum::http::StatusCode, axum::Json<QueryResponse>) {
    let query = payload.query;
    let limit = payload.limit;

    let query_model = state.query_model.clone();
    let query_qdrant = state.query_qdrant.lock().await;
    let qu_menu = state.qu_menu.clone();

    let items = query::query_menu(query, limit, query_model, &query_qdrant, qu_menu).await;

    let query_response = QueryResponse { items };

    (axum::http::StatusCode::OK, axum::Json(query_response))
}

pub async fn handle_query_modifiers(
    State(state): State<AppState>,
    axum::Json(payload): axum::Json<QueryRequest>,
) -> (axum::http::StatusCode, axum::Json<QueryResponse>) {
    let query = payload.query;
    let limit = payload.limit;
    let parent = payload.parent;

    let query_model = state.query_model.clone();
    let query_qdrant = state.query_qdrant.lock().await;
    let qu_modifiers = state.qu_modifiers.clone();

    let items = query::query_modifiers(
        query,
        limit,
        parent,
        query_model,
        &query_qdrant,
        qu_modifiers,
    )
    .await;

    let query_response = QueryResponse { items };

    (axum::http::StatusCode::OK, axum::Json(query_response))
}

pub async fn handle_get_blacklist(
    State(state): State<AppState>,
) -> (axum::http::StatusCode, axum::Json<Blacklist>) {
    let blacklist = state.blacklist.lock().await.clone();

    (axum::http::StatusCode::OK, axum::Json(blacklist))
}

pub async fn handle_post_blacklist(
    State(state): State<AppState>,
    axum::Json(payload): axum::Json<Blacklist>,
) -> (axum::http::StatusCode, axum::Json<Blacklist>) {
    let mut blacklist = state.blacklist.lock().await;

    *blacklist = payload;

    (axum::http::StatusCode::OK, axum::Json(blacklist.clone()))
}

pub async fn handle_menu(State(state): State<AppState>) -> axum::Json<qu::Menus> {
    axum::Json(state.qu_menu)
}

// nexeo will never hit this /settings endpoint, but we can use it to control the agent's behavior
pub async fn handle_settings(
    State(state): State<AppState>,
    axum::Json(client_message): axum::Json<ClientMessage>,
) -> axum::http::StatusCode {
    let ClientMessage::Settings(settings) = client_message.clone();

    *state.settings.lock().await = client_message.clone();
    info!("Updated settings: {settings:?}");

    axum::http::StatusCode::OK
}
