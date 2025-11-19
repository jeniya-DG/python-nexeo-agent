use axum::{
    extract::ws::{WebSocket, WebSocketUpgrade},
    extract::State,
    http::HeaderMap,
    response::IntoResponse,
};
use futures_util::{SinkExt, StreamExt};
use log::{debug, info, warn};
use serde::Serialize;

use crate::{AppState, CrossChannelEvent, NotCanonQueryParams};

// handles the /message endpoint that Nexeo sends text data to
pub async fn handle_message(
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

    info!("{} Nexeo connecting to /message", uid);

    if state.blacklist.lock().await.blacklist.contains(&uid) {
        return axum::http::StatusCode::NOT_FOUND.into_response();
    }

    let device_id = query_params.base_sn.unwrap_or_else(|| {
        headers
            .get("base-sn")
            .unwrap()
            .to_str()
            .unwrap()
            .to_string()
    });

    let store_id = query_params.sid_cloud_store_id.unwrap_or_else(|| {
        headers
            .get("sid-cloud-store-id")
            .unwrap()
            .to_str()
            .unwrap()
            .to_string()
    });

    // wait until the cross-channel handle has been set up by the audio handler
    // Nexeo will connect to both /audio and /message independently
    // (the choice of having the audio handler set this up is arbitrary)
    let mut iterations = 0;
    loop {
        let audio_to_message_handles = state.audio_to_message_handles.lock().await;
        if audio_to_message_handles.contains_key(&uid) {
            break;
        }
        drop(audio_to_message_handles);
        tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;

        if iterations == 4 {
            return axum::http::StatusCode::BAD_REQUEST.into_response();
        }

        iterations += 1;
    }

    ws.on_upgrade(move |socket| handle_message_socket(socket, state, uid, device_id, store_id))
}

#[derive(Serialize)]
pub struct AotNexeo {
    topic: String,
    meta: AotNexeoMeta,
    payload: AotNexeoAudioInterruptionPayload,
}

#[derive(Serialize)]
pub struct AotNexeoMeta {
    #[serde(rename = "deviceID")]
    device_id: String,
    timestamp: String,
    #[serde(rename = "msgId")]
    msg_id: String,
    #[serde(rename = "storeId")]
    store_id: String,
    #[serde(rename = "msgType")]
    msg_type: String,
}

#[derive(Serialize)]
pub struct AotNexeoAudioInterruptionPayload {
    lane: String,
}

async fn handle_message_socket(
    socket: WebSocket,
    state: AppState,
    uid: String,
    device_id: String,
    store_id: String,
) {
    info!("{uid} handle_message_socket");

    let (mut nexeo_sender, mut nexeo_receiver) = socket.split();

    // get the cross-channel rx for receiving messages from the audio ws handler
    let audio_to_message_handles = state.audio_to_message_handles.lock().await;
    let cross_channel_handle = audio_to_message_handles.get(&uid);
    // the audio handler has removed this uid
    if cross_channel_handle.is_none() {
        warn!("{uid} cross_channel_handle.is_none(), returning from /message");
        return;
    }
    // the unwrap is safe because of the check we just did
    let xch_rx = cross_channel_handle.unwrap().rx.clone();
    // we don't want to hold the lock on the HashMap,
    // just this uid's cross-channel receiver
    drop(audio_to_message_handles);
    // and finally we have received the cross-channel rx
    let mut xch_rx = xch_rx.lock().await;

    loop {
        tokio::select! {
            Some(event) = xch_rx.next() => {
                debug!("{uid} Nexeo binary->text message received: {event:?}");

                // we assume it was a UserStartedSpeaking event
                let audio_interruption = AotNexeo {
                    topic: "aot/request/audio-interruption".to_string(),
                    meta: AotNexeoMeta {
                        device_id: device_id.clone(),
                        timestamp: chrono::Local::now()
                            .to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
                        msg_id: uuid::Uuid::new_v4().to_string(),
                        store_id: store_id.clone(),
                        msg_type: "request".to_string(),
                    },
                    payload: AotNexeoAudioInterruptionPayload {
                        lane: 1.to_string(),
                    },
                };

                debug!("{uid} Sending an AudioInterruption message to Nexeo");
                let _ = nexeo_sender
                    .send(axum::extract::ws::Message::Text(
                        serde_json::to_string(&audio_interruption).unwrap().into(),
                    ))
                    .await;
            }
            Some(message) = nexeo_receiver.next() => {
                match message {
                    Ok(axum::extract::ws::Message::Text(message)) => {
                        debug!("{uid} Nexeo (text) message received: {message:?}");

                        let mut message_to_audio_handles = state.message_to_audio_handles.lock().await;

                        let cross_channel_handle = message_to_audio_handles.get_mut(&uid);
                        if cross_channel_handle.is_none() {
                            warn!("{uid} cross_channel_handle.is_none(), returning from /message");
                            return;
                        }
                        let cross_channel_handle = cross_channel_handle.unwrap();

                        if message.contains("NEXEO/request/lane1/arrive") {
                            if let Err(err) = cross_channel_handle
                                .tx
                                .send(CrossChannelEvent::Arrive)
                                .await
                            {
                                warn!("{uid} failed to send CrossChannelEvent::Arrive: {err:?}")
                            }
                        }
                        if message.contains("NEXEO/request/lane1/depart") {
                            if let Err(err) = cross_channel_handle
                                .tx
                                .send(CrossChannelEvent::Depart)
                                .await
                            {
                                warn!("{uid} failed to send CrossChannelEvent::Depart: {err:?}")
                            }
                        }
                        if message.contains("NEXEO/response/lane1-audio") && message.contains("played") {
                            if let Err(err) = cross_channel_handle
                                .tx
                                .send(CrossChannelEvent::Played)
                                .await
                            {
                                warn!("{uid} failed to send CrossChannelEvent::Played: {err:?}")
                            }
                        }

                        if message.contains("NEXEO/alert/crew-escalation/lane1") {
                            if let Err(err) = cross_channel_handle
                                .tx
                                .send(CrossChannelEvent::Escalation)
                                .await
                            {
                                warn!("{uid} failed to send CrossChannelEvent::Escalation: {err:?}")
                            }
                        }

                    }
                    _ => {}
                }
            }
            else => break,
        }
    }
}
