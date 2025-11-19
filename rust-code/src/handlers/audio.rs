use std::sync::Arc;

use axum::{
    extract::ws::{WebSocket, WebSocketUpgrade},
    extract::State,
    http::HeaderMap,
    response::IntoResponse,
};
use futures::stream::{SplitSink, SplitStream};
use futures_util::{SinkExt, StreamExt};
use log::{debug, error, info, trace, warn};
use serde_json::{json, Value};
use tokio::net::TcpStream;
use tokio::sync::Mutex;
use tokio_tungstenite::{
    connect_async,
    tungstenite::{client::IntoClientRequest, http::HeaderValue},
};
use tokio_tungstenite::{MaybeTlsStream, WebSocketStream};

use crate::{
    api::{QueryResponse, ServerMessage},
    persistence::persist_order,
    qu, query, AppState, CrossChannelEvent, ENABLE_BARGE_IN,
};
use crate::{CrossChannelHandles, NotCanonQueryParams};

/// handles the /audio endpoint that Nexeo sends binary data to
/// 1. extracts the store uid
/// 2. checks it against the blacklist
/// 3. sets up the cross-channel event handlers and adds them to the app state
/// 4. upgrades the websocket and spins up `handle_audio_socket`
pub async fn handle_audio(
    State(state): State<AppState>,
    axum::extract::Query(query_params): axum::extract::Query<NotCanonQueryParams>,
    headers: HeaderMap,
    ws: WebSocketUpgrade,
) -> impl IntoResponse {
    debug!("{:?}", &headers);
    dbg!(&query_params);

    // TODO: return an error
    let uid = query_params.sid_cloud_store_uid.unwrap_or_else(|| {
        headers
            .get("sid-cloud-store-uid")
            .unwrap()
            .to_str()
            .unwrap()
            .to_string()
    });

    info!("{uid} Nexeo connecting to /audio");

    if state.blacklist.lock().await.blacklist.contains(&uid) {
        return axum::http::StatusCode::NOT_FOUND.into_response();
    }

    // insert a new cross-channel handle
    // so that the audio / binary ws handler can send messages to the message / text ws handler
    let audio_to_message_handles = state.audio_to_message_handles.clone();
    let mut audio_to_message_handles = audio_to_message_handles.lock().await;

    let (tx, rx) = futures::channel::mpsc::channel::<CrossChannelEvent>(10);
    audio_to_message_handles.insert(
        uid.clone(),
        CrossChannelHandles {
            tx,
            rx: Arc::new(Mutex::new(rx)),
        },
    );

    // insert a new cross-channel handle
    // so that the message / text ws handler can send messages to the audio / binary ws handler
    let message_to_audio_handles = state.message_to_audio_handles.clone();
    let mut message_to_audio_handles = message_to_audio_handles.lock().await;

    let (tx, rx) = futures::channel::mpsc::channel::<CrossChannelEvent>(10);
    message_to_audio_handles.insert(
        uid.clone(),
        CrossChannelHandles {
            tx,
            rx: Arc::new(Mutex::new(rx)),
        },
    );

    ws.on_upgrade(move |socket| handle_audio_socket(socket, state, uid))
}

async fn handle_audio_socket(socket: WebSocket, state: AppState, uid: String) {
    info!("{uid} handle_audio_socket");

    // 1. split the websocket
    let (mut nexeo_sender, mut nexeo_receiver) = socket.split();

    // 2. get the cross-channel rx for receiving messages from the audio / binary ws handler
    let message_to_audio_handles = state.message_to_audio_handles.lock().await;
    let cross_channel_handle = message_to_audio_handles.get(&uid);
    if cross_channel_handle.is_none() {
        warn!("{uid} cross-channel handle is gone?");
        return;
    }
    let xch_rx = cross_channel_handle.unwrap().rx.clone();
    // we don't want to hold the lock on the HashMap, just this uid's cross-channel receiver
    drop(message_to_audio_handles);
    // and finally we have received the cross-channel rx
    let mut xch_rx = xch_rx.lock().await;

    // 3. initialize some state
    let mut dg_request_id = None;
    let mut qu_order_id = None;

    let mut sts_receiver: Option<SplitStream<WebSocketStream<MaybeTlsStream<TcpStream>>>> = None;
    let mut sts_sender: Option<
        SplitSink<
            WebSocketStream<MaybeTlsStream<TcpStream>>,
            tokio_tungstenite::tungstenite::Message,
        >,
    > = None;

    let mut agent_speaking = false;
    let mut buffered_audio = Vec::new();

    // 4. we used to optionally set up an echo cancellator here

    // 5. finally, we run the main loop for this handler
    loop {
        tokio::select! {
            Some(event) = xch_rx.next() => {
                debug!("{uid} Nexeo text->binary message received: {event:?}",);

                match event {
                    CrossChannelEvent::Arrive => {
                        // connect to Deepgram STS
                        let mut request = url::Url::parse(&state.deepgram_agent_url)
                            .unwrap()
                            .into_client_request()
                            .unwrap();
                        let headers = request.headers_mut();
                        headers.insert(
                            "Authorization",
                            HeaderValue::from_str(&format!("Token {}", state.deepgram_api_key))
                                .unwrap(),
                        );

                        let (ws, response) = connect_async(request)
                            .await
                            .expect("Failed to connect to STS.");

                        // TODO: use this to get the dg_request_id
                        dbg!(&response);

                        let (mut tx, rx) = ws.split();

                        let settings = state.settings.lock().await.clone();

                        // send the initial config message to Deepgram STS
                        let settings_json = serde_json::to_string(&settings).unwrap();
                        tx
                            .send(tokio_tungstenite::tungstenite::Message::Text(
                                settings_json.into(),
                            ))
                            .await
                            .unwrap();

                        qu_order_id = Some(qu::orders(state.qu_jwt.clone(), state.qu_menu.value.as_ref().unwrap().snapshot_id.clone())
                            .await
                            .value
                            .order
                            .id);

                        sts_receiver = Some(rx);
                        sts_sender = Some(tx);
                    }
                    CrossChannelEvent::Depart => {
                        persist_order(state.qu_jwt.clone(), qu_order_id.clone(), dg_request_id.clone(), "depart".to_string()).await;

                        qu_order_id = None;
                        sts_receiver = None;
                        sts_sender = None;

                        info!("{uid} agent_speaking value on depart: {:?}", agent_speaking);
                        buffered_audio = Vec::new();
                        agent_speaking = false;
                    }
                    CrossChannelEvent::Played => {
                        agent_speaking = false;
                        if !agent_speaking && !buffered_audio.is_empty() {
                            info!("{uid} sending {} bytes of buffered audio to Nexeo", buffered_audio.len());

                            let payload = buffered_audio;
                            let checksum = crc32fast::hash(&payload);

                            let mut message = Vec::new();
                            message.extend_from_slice(&checksum.to_be_bytes());
                            message.push(0);
                            message.extend_from_slice(&[0u8; 11]);
                            message.extend_from_slice(&payload);

                            if let Err(err) = nexeo_sender
                                .send(axum::extract::ws::Message::Binary(message.into()))
                                .await
                            {
                                warn!("{uid} failed to send audio to Nexeo: {err:?}");
                            }
                            buffered_audio = Vec::new();
                            agent_speaking = true;
                        }
                    }
                    CrossChannelEvent::Escalation => {
                        persist_order(state.qu_jwt.clone(), qu_order_id.clone(), dg_request_id.clone(), "escalation".to_string()).await;

                        qu_order_id = None;
                        sts_receiver = None;
                        sts_sender = None;

                        info!("{uid} agent_speaking value on escalation: {:?}", agent_speaking);
                        buffered_audio = Vec::new();
                        agent_speaking = false;
                    }
                    _ => {
                        warn!("{uid} unhandled CrossChannelEvent");
                    }
                }
            }
            Some(message) = async {
                if let Some(receiver) = &mut sts_receiver {
                    receiver.next().await
                } else {
                    None
                }
            } => {
                // TODO: fix the unwrap
                let message = message.unwrap();
                match message {
                    tokio_tungstenite::tungstenite::Message::Text(message) => {
                        if let Ok(message) = serde_json::from_str::<ServerMessage>(&message) {
                            match message {
                                ServerMessage::Welcome { session_id } => {
                                    // TODO: try to get from headers
                                    dg_request_id = Some(session_id);
                                },
                                ServerMessage::UserStartedSpeaking => {
                                    if ENABLE_BARGE_IN {
                                        let mut audio_to_message_handles =
                                        state.audio_to_message_handles.lock().await;

                                        let cross_channel_handle =
                                            audio_to_message_handles.get_mut(&uid);
                                        if cross_channel_handle.is_none() {
                                            warn!("{uid} cross_channel_handle.is_none(), returning from /audio");
                                            return;
                                        }
                                        let cross_channel_handle = cross_channel_handle.unwrap();

                                        cross_channel_handle
                                            .tx
                                            .send(CrossChannelEvent::UserStartedSpeaking)
                                            .await
                                            .unwrap();
                                    }
                                },
                                ServerMessage::FunctionCallRequest { functions } => {
                                    for f in functions {
                                        if !f.client_side {
                                            debug!("{uid} skipping server-side function: {} ({})", f.name, f.id);
                                            continue;
                                        }

                                        let function_name = f.name.clone();
                                        let function_call_id = f.id.clone();

                                        let input: Value = match serde_json::from_str(&f.arguments) {
                                            Ok(v) => v,
                                            Err(e) => {
                                                warn!("{uid} invalid arguments JSON for {} ({}): {}", function_name, function_call_id, e);
                                                let function_call_response = json!({
                                                    "type": "FunctionCallResponse",
                                                    "id": function_call_id,
                                                    "name": function_name,
                                                    "content": format!("{{\"error\":\"invalid arguments JSON: {}\"}}", e)
                                                });
                                                if let Some(ref mut sender) = sts_sender {
                                                    let _ = sender.send(tokio_tungstenite::tungstenite::Message::Text(function_call_response.to_string().into())).await;
                                                }
                                                continue;
                                            }
                                        };

                                        if function_name == "query_items" {
                                            let query = input["query"].as_str().unwrap_or_default().to_string();

                                            info!("{uid} query: {query}");

                                            let limit = input.get("limit")
                                                .and_then(|v| v.as_u64());

                                            info!("{uid} limit: {limit:?}");

                                            let query_model = state.query_model.clone();
                                            let query_qdrant = state.query_qdrant.lock().await;
                                            let qu_menu = state.qu_menu.clone();

                                            let items = query::query_menu(
                                                query.to_string(),
                                                limit,
                                                query_model,
                                                &query_qdrant,
                                                qu_menu,
                                            ).await;

                                            let query_response = QueryResponse { items };

                                            info!("{uid} query response: {query_response:?}");

                                            let function_call_response = json!({
                                                "type": "FunctionCallResponse",
                                                "id": function_call_id,
                                                "name": function_name,
                                                "content": serde_json::to_string(&query_response).expect("Failed to serialize query response.")
                                            });

                                            if let Some(ref mut sender) = sts_sender {
                                                let _ = sender.send(tokio_tungstenite::tungstenite::Message::Text(function_call_response.to_string().into())).await;
                                            }
                                        }

                                        if function_name == "query_modifiers" {
                                            let query = input["query"].as_str().unwrap_or_default().to_string();
                                            // TODO: consider making parent optional
                                            let parent = input["parent"].as_str().unwrap_or_default().to_string();

                                            info!("{uid} query: {query} with parent: {parent}");

                                            let limit = input.get("limit")
                                                .and_then(|v| v.as_u64());

                                            info!("{uid} limit: {limit:?}");

                                            let query_model = state.query_model.clone();
                                            let query_qdrant = state.query_qdrant.lock().await;
                                            let qu_modifiers = state.qu_modifiers.clone();

                                            let items = query::query_modifiers(
                                                query.to_string(),
                                                limit,
                                                Some(parent),
                                                query_model,
                                                &query_qdrant,
                                                qu_modifiers,
                                            ).await;

                                            let query_response = QueryResponse { items };

                                            info!("{uid} query response: {query_response:?}");

                                            let function_call_response = json!({
                                                "type": "FunctionCallResponse",
                                                "id": function_call_id,
                                                "name": function_name,
                                                "content": serde_json::to_string(&query_response).expect("Failed to serialize query response.")
                                            });

                                            if let Some(ref mut sender) = sts_sender {
                                                let _ = sender.send(tokio_tungstenite::tungstenite::Message::Text(function_call_response.to_string().into())).await;
                                            }
                                        }

                                        if function_name == "add_item" {
                                            let item_path_key = input["itemPathKey"].as_str().unwrap_or_default().to_string();
                                            info!("{uid} Looking up item by item path key: {item_path_key:?}");
                                            let qu_menu = state.qu_menu.clone();
                                            let item = qu::find_item(&qu_menu, item_path_key.to_string()).await;
                                            info!("{uid} Adding item to order: {item:?}");

                                            let output = if let (Some(item), Some(qu_order_id)) = (item.clone(), qu_order_id.clone()) {
                                                match qu::add_item(
                                                    state.qu_jwt.clone(),
                                                    qu_order_id,
                                                    item.item_path_key,
                                                )
                                                .await {
                                                    Ok(order) => {
                                                        info!("{uid} Successfully added item to order: {order}");
                                                        order
                                                    },
                                                    Err(error) => error
                                                }
                                            } else {
                                                "Failed - item and/or order error.".to_string()
                                            };

                                            let function_call_response = json!({
                                                "type": "FunctionCallResponse",
                                                "id": function_call_id,
                                                "name": function_name,
                                                "content": output
                                            });

                                            if let Some(ref mut sender) = sts_sender {
                                                let _ = sender.send(tokio_tungstenite::tungstenite::Message::Text(function_call_response.to_string().into())).await;
                                            }
                                        }

                                        if function_name == "delete_item" {
                                            let item_id = input["itemId"].as_str().unwrap_or_default().to_string();

                                            let output = if let Some(qu_order_id) = qu_order_id.clone() {
                                                qu::delete_item(
                                                    state.qu_jwt.clone(),
                                                    qu_order_id,
                                                    item_id,
                                                )
                                                .await
                                            } else {
                                                "Failed - order not present.".to_string()
                                            };

                                            let function_call_response = json!({
                                                "type": "FunctionCallResponse",
                                                "id": function_call_id,
                                                "name": function_name,
                                                "content": output
                                            });

                                            if let Some(ref mut sender) = sts_sender {
                                                let _ = sender.send(tokio_tungstenite::tungstenite::Message::Text(function_call_response.to_string().into())).await;
                                            }
                                        }

                                        if function_name == "add_modifier" {
                                            let item_id = input["itemId"].as_str().unwrap_or_default().to_string();
                                            let item_path_key = input["itemPathKey"].as_str().unwrap_or_default().to_string();
                                            error!("{uid} Looking up modifier by item path key: {item_path_key:?}");
                                            let qu_modifiers = state.qu_modifiers.clone();
                                            let modifier = qu::find_modifier(&qu_modifiers, item_path_key.to_string()).await;

                                            // TODO: at this point, we could verify that the item_id corresponds to an item
                                            // whose item_path_key is a parent of the modifier's item_path_key

                                            error!("{uid} Adding modifier ({modifier:?}) to item ({item_id:?}).");

                                            let output = if let (Some(modifier), Some(qu_order_id)) = (modifier.clone(), qu_order_id.clone()) {
                                                match qu::add_modifier(
                                                    state.qu_jwt.clone(),
                                                    qu_order_id,
                                                    item_id,
                                                    modifier.item_path_key
                                                )
                                                .await {
                                                    Ok(order) => {
                                                        info!("{uid} Successfully added modifier to item: {order}");
                                                        order
                                                    },
                                                    Err(error) => error
                                                }
                                            } else {
                                                "Failed - item and/or order error.".to_string()
                                            };

                                            let function_call_response = json!({
                                                "type": "FunctionCallResponse",
                                                "id": function_call_id,
                                                "name": function_name,
                                                "content": output
                                            });

                                            if let Some(ref mut sender) = sts_sender {
                                                let _ = sender.send(tokio_tungstenite::tungstenite::Message::Text(function_call_response.to_string().into())).await;
                                            }
                                        }

                                        if function_name == "order" {
                                            let output = if let Some(qu_order_id) = qu_order_id.clone() {
                                                qu::order(state.qu_jwt.clone(), qu_order_id).await
                                            } else {
                                                error!("{uid} somehow an order id is not present despite ongoing conversation!");
                                                "Failed - no order present.".to_string()
                                            };

                                            let function_call_response = json!({
                                                "type": "FunctionCallResponse",
                                                "id": function_call_id,
                                                "name": function_name,
                                                "content": output
                                            });

                                            if let Some(ref mut sender) = sts_sender {
                                                let _ = sender.send(tokio_tungstenite::tungstenite::Message::Text(function_call_response.to_string().into())).await;
                                            }
                                        }
                                    }
                                }

                            }
                        } else {
                            info!("{uid} {message}");
                        }
                    }
                    tokio_tungstenite::tungstenite::Message::Binary(audio) => {
                        if !agent_speaking {
                            trace!("{uid} sending {} bytes of audio to Nexeo", audio.len());

                            // we are using "stream": false
                            // this means each binary message received is a full sentence of audio that we can send to Nexeo
                            let payload = audio;
                            let checksum = crc32fast::hash(&payload);

                            let mut message = Vec::new();
                            message.extend_from_slice(&checksum.to_be_bytes());
                            message.push(0);
                            message.extend_from_slice(&[0u8; 11]);
                            message.extend_from_slice(&payload);

                            if let Err(err) = nexeo_sender
                                .send(axum::extract::ws::Message::Binary(message.into()))
                                .await
                            {
                                warn!("{uid} failed to send audio to Nexeo: {err:?}");
                            }

                            agent_speaking = true;
                        } else {
                            debug!("{uid} buffering audio to send to Nexeo");
                            buffered_audio.extend(audio);
                        }
                    },
                    tokio_tungstenite::tungstenite::Message::Close(_) => {
                        persist_order(state.qu_jwt.clone(), qu_order_id.clone(), dg_request_id.clone(), "close".to_string()).await;
                    },
                    _ => {}
                }
            }
            Some(message) = nexeo_receiver.next() => {
                match message {
                    Ok(axum::extract::ws::Message::Binary(message)) => {
                        if !ENABLE_BARGE_IN && agent_speaking {
                            debug!("{uid} Agent is speaking, so skipping sending this audio.");

                            if let Some(ref mut sender) = sts_sender {
                                let keep_alive = serde_json::json!({
                                    "type": "KeepAlive"
                                });
                                let message = tokio_tungstenite::tungstenite::Message::Text(keep_alive.to_string().into());
                                let _ = sender.send(message).await;
                            }

                            continue;
                        }

                        if let Some(ref mut sender) = sts_sender {
                            let mut capture_frame = Vec::new();

                            // 1. extract the capture/mic
                            let sample_num = message.len() / 4;
                            for index in 0..sample_num {
                                capture_frame.push(message[0 + index * 4]);
                                capture_frame.push(message[1 + index * 4]);
                            }

                            // 2. send the capture/mic audio to STS
                            sender
                                .send(tokio_tungstenite::tungstenite::Message::Binary(
                                    capture_frame.into(),
                                ))
                                .await
                                .unwrap();
                        } else {
                            trace!("{uid} we got audio from Nexeo, but the vehicle detector hasn't triggered yet!");
                        }
                    },
                    _ => {}
                }
            }
            else => break,
        }
    }
}
