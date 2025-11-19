use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::Read;
use std::path::Path;
use std::sync::Arc;
use std::time::Instant;

use axum::routing::{get, post};
use axum::Router;
use axum_server::Handle;
use log::info;
use qdrant_client::Qdrant;
use qu::Menus;
use rust_bert::pipelines::sentence_embeddings::SentenceEmbeddingsModel;
use serde::Deserialize;
use serde_json::json;
use tokio::sync::Mutex;

use crate::api::{Blacklist, ClientMessage};
use crate::handlers::audio::handle_audio;
use crate::handlers::http::{
    handle_get_blacklist, handle_menu, handle_post_blacklist, handle_query_items,
    handle_query_modifiers, handle_settings,
};
use crate::handlers::message::handle_message;

pub mod api;
pub mod handlers;
pub mod persistence;
pub mod qu;
pub mod query;

const ENABLE_BARGE_IN: bool = false;

#[derive(Clone)]
pub struct AppState {
    blacklist: Arc<Mutex<Blacklist>>,
    settings: Arc<Mutex<ClientMessage>>,
    deepgram_api_key: String,
    deepgram_agent_url: String,
    qu_jwt: String,
    qu_menu: qu::Menus,
    qu_modifiers: HashMap<String, qu::Descendants>,
    query_model: Arc<Mutex<SentenceEmbeddingsModel>>,
    query_qdrant: Arc<Mutex<Qdrant>>,
    audio_to_message_handles: Arc<Mutex<HashMap<String, CrossChannelHandles>>>,
    message_to_audio_handles: Arc<Mutex<HashMap<String, CrossChannelHandles>>>,
}

/// these represent the sending and receiving handlers for events
/// that are sent between the /audio and /message websocket handlers
pub struct CrossChannelHandles {
    tx: futures::channel::mpsc::Sender<CrossChannelEvent>,
    rx: Arc<Mutex<futures::channel::mpsc::Receiver<CrossChannelEvent>>>,
}

/// these define the types of events the /audio and /message websocket
/// handlers can send to each other
#[derive(Debug)]
pub enum CrossChannelEvent {
    UserStartedSpeaking,
    Arrive,
    Depart,
    Played,
    Escalation,
}

/// these can be used by web clients mimicking a Nexeo box
/// since web clients cannot freely send these as headers,
/// we allow them to be sent as query parameters
#[derive(Deserialize, Debug)]
pub struct NotCanonQueryParams {
    #[serde(rename = "sid-cloud-store-uid")]
    pub sid_cloud_store_uid: Option<String>,
    #[serde(rename = "sid-cloud-store-id")]
    pub sid_cloud_store_id: Option<String>,
    #[serde(rename = "base-sn")]
    pub base_sn: Option<String>,
}

#[tokio::main]
async fn main() {
    // Install default crypto provider for rustls
    rustls::crypto::ring::default_provider()
        .install_default()
        .expect("Failed to install rustls crypto provider");
    
    env_logger::init();

    let start = Instant::now();

    let deepgram_api_key = std::env::var("DEEPGRAM_API_KEY").unwrap();
    let deepgram_agent_url = std::env::var("DEEPGRAM_AGENT_URL").unwrap_or_else(|_| "wss://agent.deepgram.com/v1/agent/converse".to_string());
    let qu_secret = std::env::var("QU_SECRET").unwrap();

    info!("[1/4] Obtaining Qu JWT...");
    let qu_jwt = qu::jwt(qu_secret).await;
    info!("[1/4] Qu JWT obtained");

    info!("[2/4] Checking for cached menu...");
    let menu_directory = std::env::var("MENU_DIRECTORY").unwrap_or("./menu".to_string());
    let menu_path = format!("{}/menu.json", menu_directory);
    let modifiers_path = format!("{}/modifiers.json", menu_directory);

    let qu_menu = if Path::new(&menu_path).exists() {
        info!("[2/4] Found cached menu, loading from disk");
        let mut file = File::open(menu_path).expect("Failed to open menu file.");
        let mut contents = String::new();
        file.read_to_string(&mut contents)
            .expect("Failed to read from menu file.");

        let menu: Menus =
            serde_json::from_str(&contents).expect("Failed to deserialize menu JSON.");
        menu
    } else {
        info!("[2/4] No cached menu found, fetching from Qu API...");
        let menu = qu::menus(qu_jwt.clone()).await;

        // Ensure directory exists before creating file
        std::fs::create_dir_all(&menu_directory).expect("Failed to create menu directory.");
        let file = File::create(menu_path).expect("Failed to create menu file.");
        serde_json::to_writer(file, &menu).expect("Failed to write to menu file.");
        menu
    };

    info!(
        "[2/4]  Menu loaded successfully (snapshot: {})",
        qu_menu.value.as_ref().unwrap().snapshot_id
    );

    let mut qu_modifiers = HashMap::new();

    if Path::new(&modifiers_path).exists() {
        info!("[3/4]  Found cached modifiers, loading from disk");

        let file = File::open(modifiers_path).expect("Failed to open modifiers file.");
        qu_modifiers =
            serde_json::from_reader(file).expect("Failed to deserialize modifiers JSON.");
    } else {
        info!("[3/4] No cached modifiers found, fetching from Qu API...");

        let total = qu_menu.value.as_ref().unwrap().categories.len();
        let mut count = 0;
        for category in &qu_menu.value.as_ref().unwrap().categories {
            for item in &category.children {
                let descendants = qu::descendants(
                    qu_jwt.clone(),
                    qu_menu.value.as_ref().unwrap().snapshot_id.clone(),
                    item.item_path_key.clone(),
                )
                .await;

                qu_modifiers.insert(item.item_path_key.clone(), descendants);
            }
            count += 1;

            let progress = (count as f32 / total as f32 * 100.0) as u32;
            info!("[3/4] Progress: {progress}% ({count}/{total} categories processed)");
        }

        let file = File::create(modifiers_path).expect("Failed to create modifiers file.");
        serde_json::to_writer(file, &qu_modifiers).expect("Failed to write to modifiers file.");
        info!("[3/4]  Modifiers cached successfully");
    }

    info!("[4/4] Initializing query system...");
    let query_model = query::model().await;
    let query_qdrant = query::qdrant(&qu_menu, &qu_modifiers, &query_model).await;
    info!("[4/4]  Query system initialized");

    let settings = json!({
        "type": "Settings",
        "audio": {
            "input": {
                "encoding": "linear16",
                "sample_rate": 48000
            },
            "output": {
                "encoding": "linear16",
                "sample_rate": 16000,
                "container": "none"
            }
        },
        "agent": {
            "language": "en",
            "listen": {
                "provider": {
                    "type": "deepgram",
                    "model": "nova-3",
                    "keyterms": ["Hi-C", "Barq's", "Coca-cola", "Coke", "Fanta", "Iced Coffee"],
                }
            },
            "think": {
                "provider": {
                    "type": "open_ai",
                    "model": "gpt-4o",
                    "temperature": 0.7
                },
                "prompt": r#"You work taking orders at a Jack in the Box drive-thru. Follow these instructions strictly. Do not deviate:
                (1) Never speak in full sentences. Speak in short, yet polite responses.
                (2) Never repeat the customer's order back to them unless they ask for it.
                (3) If someone orders a breakfast item, ask if they would like an orange juice with that.
                (4) If someone orders a small or regular, ask "Would like to make that a large?".
                (5) Don't mention prices until the customer confirms that they're done ordering.
                (6) Allow someone to mix and match sizes for combos.
                (7) At the end of the order, If someone has not ordered a dessert item AND has not ordered a breakfast item, ask if they would like to add a dessert.
                (8) If someones changes their single item orders to a combo, remove the previous single item order.
                (9) Don't respond with ordered lists.
                (10) When someone orders a combo, make sure to get their side and drink specifications before moving on to the next item.
                (11) Function rules (must follow):
                    (A) For any request about availability, items, combos, or “do you have X?”, FIRST call query_items with the user phrase as query (limit 8). Do not answer from memory.
                    (B) Never say an item is unavailable unless query_items did not return a relevant result; instead, ask a short clarifying question and retry query_items.
                    (C) When the user confirms an item from results, call add_item with the returned itemPathKey.
                    (D) Keep replies short; use functions to ground facts.
                
                (12) Sometimes, people will order combos by their combo numbers. Here is a mapping of combo numbers to their respective items:
                  [
                      { "combo_number": 1, "combo_name": "Sourdough Jack" },
                      { "combo_number": 2, "combo_name": "Double Jack" },
                      { "combo_number": 3, "combo_name": "Swiss Buttery Jack" },
                      { "combo_number": 4, "combo_name": "Bacon Ultimate Cheeseburger" },
                      { "combo_number": 5, "combo_name": "Bacon Double SmashJack" },
                      { "combo_number": 6, "combo_name": "Jumbo Jack Cheeseburger" },
                      { "combo_number": 6, "combo_name": "Jumbo Jack" },
                      { "combo_number": 7, "combo_name": "Butter SmashJack" },
                      { "combo_number": 8, "combo_name": "Ultimate Cheeseburger" },
                      { "combo_number": 9, "combo_name": "Smash Jack" },
                      { "combo_number": 10, "combo_name": "Homestyle Chicken" },
                      { "combo_number": 11, "combo_name": "Cluck Chicken" },
                      { "combo_number": 12, "combo_name": "8 Piece Nuggets" },
                      { "combo_number": 13, "combo_name": "Crispy Chicken Strips (5pc)" },
                      { "combo_number": 13, "combo_name": "Crispy Chicken Strips (3pc)" },
                      { "combo_number": 14, "combo_name": "Spicy Chicken" },
                      { "combo_number": 14, "combo_name": "Spicy Chicken Cheese" },
                      { "combo_number": 15, "combo_name": "Grilled Chicken Sandwich" },
                      { "combo_number": 16, "combo_name": "Chicken Teriyaki Bowl" },
                      { "combo_number": 17, "combo_name": "Chicken Fajita Wrap" },
                      { "combo_number": 18, "combo_name": "Garden Salad" },
                      { "combo_number": 18, "combo_name": "Garden Crispy Chicken Salad Combo" },
                      { "combo_number": 18, "combo_name": "Garden Grilled Chicken Salad Combo" },
                      { "combo_number": 18, "combo_name": "Garden Salad, No Chicken" },
                      { "combo_number": 19, "combo_name": "Southwest Salad" },
                      { "combo_number": 19, "combo_name": "Southwest Crispy Chicken Salad Combo" },
                      { "combo_number": 19, "combo_name": "Southwest Grilled Chicken Salad Combo" },
                      { "combo_number": 19, "combo_name": "Southwest Salad, No Chicken" },
                      { "combo_number": 21, "combo_name": "Supreme Croissant" },
                      { "combo_number": 22, "combo_name": "Sausage Croissant" },
                      { "combo_number": 23, "combo_name": "Loaded Breakfast" },
                      { "combo_number": 24, "combo_name": "Supreme Sourdough Breakfast" },
                      { "combo_number": 25, "combo_name": "Ultimate Breakfast" },
                      { "combo_number": 26, "combo_name": "Extreme Sausage" },
                      { "combo_number": 27, "combo_name": "Meat Lover Burrito" },
                      { "combo_number": 28, "combo_name": "3pc French Toast Platter Bacon" },
                      { "combo_number": 28, "combo_name": "3pc French Toast Platter Sausage" },
                      { "combo_number": 28, "combo_name": "3pc French Toast Platter Bacon Sausage" },
                      { "combo_number": 29, "combo_name": "6pc French Toast" }
                  ]"#,
                "functions": [
                    {
                      "name": "order",
                      "description": "Call this to get all details about the current order. For example, it will give you the id of every item added to the order.",
                      "parameters": {
                        "type": "object",
                        "properties": {
                        },
                        "required": [
                        ]
                      }
                    },
                    {
                      "name": "query_items",
                      "description": "Call this to query the available items and to verify the item the user may be requesting.
                      This function will return the items on the menu closest to what the user asked for,
                      including important information for other function calls, like the itemPathKey.",
                      "parameters": {
                        "type": "object",
                        "properties": {
                          "query": {
                            "type": "string",
                            "description": "A query for the item the user is interested in."
                          },
                          "limit": {
                            "type": "integer",
                            "description": "The number of results to return. The default is 5. If it seems like the item might be found if more results are returned, specify a larger value."
                          }
                        },
                        "required": [
                          "query"
                        ]
                      }
                    },
                    {
                      "name": "query_modifiers",
                      "description": "Call this to query the available modifiers on items, such as sauces, sides, toppics, etc,
                      and to verify the modifier the user may be requesting.
                      This function will return the modifiers on the menu closest to what the user asked for,
                      including important information for other function calls, like the itemPathKey.",
                      "parameters": {
                        "type": "object",
                        "properties": {
                          "query": {
                            "type": "string",
                            "description": "A query for the modifier the user is interested in."
                          },
                          "parent": {
                            "type": "string",
                            "description": "The itemPathKey of the parent item that this modifier modifies."
                          },
                          "limit": {
                            "type": "integer",
                            "description": "The number of results to return. The default is 5. If it seems like the item might be found if more results are returned, specify a larger value."
                          }
                        },
                        "required": [
                          "query",
                          "parent"
                        ]
                      }
                    },
                    {
                      "name": "add_item",
                      "description": "Add an item to the order. When the user has confirmed they want this item added to their order, call this function.
                      Make sure you first obtain the itemPathKey by calling the query_item function before calling this function.",
                      "parameters": {
                        "type": "object",
                        "properties": {
                          "itemPathKey": {
                            "type": "string",
                            "description": "The unique item path key identifying the item."
                          }
                        },
                        "required": [
                          "itemPathKey"
                        ]
                      }
                    },
                    {
                      "name": "delete_item",
                      "description": "Deletes an item to the order.
                      Make sure you first obtain the itemId by calling the order function before calling this function.",
                      "parameters": {
                        "type": "object",
                        "properties": {
                          "itemId": {
                            "type": "string",
                            "description": "The unique item id identifying the item in the order."
                          }
                        },
                        "required": [
                          "itemId"
                        ]
                      }
                    },
                    {
                      "name": "add_modifier",
                      "description": "Adds a modifier to an item on an order.
                      Make sure you first obtain the itemId of the item and the itemPathKey of the modifier
                      by calling other functions before calling this function.",
                      "parameters": {
                        "type": "object",
                        "properties": {
                          "itemPathKey": {
                            "type": "string",
                            "description": "The unique item path key identifying the modifier."
                          },
                          "itemId": {
                            "type": "string",
                            "description": "The unique item id identifying the item in the order."
                          }
                        },
                        "required": [
                          "itemPathKey",
                          "itemId"
                        ]
                      }
                    }
                  ]
            },
            "speak": {
                "provider": {
                    "type": "deepgram",
                    "model": "aura-2-thalia-en"
                }
            },
            "greeting": "Welcome to Jack in the Box. What can I get for you today?"
        }
    });

    let settings: ClientMessage = serde_json::from_value(settings).unwrap();

    let mut blacklist = HashSet::new();
    blacklist.insert("3E0245C352A345278CCE30FD262449CE".to_string());

    let blacklist = Arc::new(Mutex::new(Blacklist { blacklist }));

    let state = AppState {
        blacklist,
        settings: Arc::new(Mutex::new(settings)),
        deepgram_api_key,
        deepgram_agent_url,
        qu_jwt,
        qu_menu,
        qu_modifiers,
        query_model: Arc::new(Mutex::new(query_model)),
        query_qdrant: Arc::new(Mutex::new(query_qdrant)),
        audio_to_message_handles: Arc::new(Mutex::new(HashMap::new())),
        message_to_audio_handles: Arc::new(Mutex::new(HashMap::new())),
    };

    let elapsed = start.elapsed();
    info!("Start up took {elapsed:?} seconds.");

    let app = Router::new()
        .route("/audio", get(handle_audio))
        .route("/message", get(handle_message))
        .route("/settings", post(handle_settings))
        .route("/menu", get(handle_menu))
        .route("/blacklist", get(handle_get_blacklist))
        .route("/blacklist", post(handle_post_blacklist))
        .route("/query/items", post(handle_query_items))
        .route("/query/modifiers", post(handle_query_modifiers))
        .with_state(state);

    let server_handle = Handle::new();

    axum_server::bind("0.0.0.0:4000".parse().unwrap())
        .handle(server_handle)
        .serve(app.into_make_service())
        .await
        .unwrap();
}
