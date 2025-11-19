use std::collections::HashMap;
use std::collections::VecDeque;
use std::sync::OnceLock;

use log::error;
use serde::{Deserialize, Serialize};

static QU_BASE_URL: OnceLock<String> = OnceLock::new();

fn get_qu_base_url() -> &'static str {
    QU_BASE_URL.get_or_init(|| {
        std::env::var("QU_BASE_URL")
            .expect("QU_BASE_URL environment variable must be set")
    })
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct Menus {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub value: Option<MenusValue>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub succeed: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub errors: Option<Vec<QuError>>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct QuError {
    pub code: i32,
    pub key: String,
    pub message: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct MenusValue {
    pub snapshot_id: String,
    pub categories: Vec<Item>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct Modifiers {
    pub modifiers: HashMap<String, Descendants>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct Descendants {
    pub value: Vec<Item>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct DescendantsValue {
    pub children: Vec<Item>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct Item {
    pub title: String,
    pub item_path_key: String,
    pub parent_path_key: String,
    pub display_attribute: DisplayAttribute,
    pub children: Vec<Item>,
    #[serde(default = "uuid::Uuid::new_v4")]
    pub query_id: uuid::Uuid,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct DisplayAttribute {
    pub description: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct Orders {
    pub value: OrdersValue,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct OrdersValue {
    pub order: Order,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct Order {
    pub id: String,
}

pub async fn jwt(secret: String) -> String {
    let client = reqwest::Client::new();

    let url = format!("{}/authentication/oauth2/access-token", get_qu_base_url());
    let client_id = std::env::var("CLIENT_ID").expect("CLIENT_ID environment variable not set");
    
    log::info!("Making JWT request to: {}", url);
    log::info!("Equivalent curl command:");
    log::info!("curl -X POST '{}' \\", url);
    log::info!("  -F 'grant_type=client_credentials' \\");
    log::info!("  -F 'client_id={}' \\", client_id);
    log::info!("  -F 'client_secret: [REDACTED]'");
    log::info!("  -F 'scope=menu:*'");
    log::info!("");

    let response = client
        .post(url)
        .multipart(
            reqwest::multipart::Form::new()
                .text("grant_type", "client_credentials")
                .text("client_id", client_id)
                .text("client_secret", secret)
                .text("scope", "menu:*"),
        )
        .send()
        .await
        .expect("Failed to make HTTP request to Qu for JWT.");

    let json_response: serde_json::Value = response
        .json()
        .await
        .expect("Failed to parse Qu response as json.");

    log::debug!("Qu API response: {}", json_response);

    let qu_jwt = json_response["access_token"]
        .as_str()
        .unwrap_or_else(|| {
            log::error!("Failed to get access_token from Qu response. Full response: {}", json_response);
            panic!("Failed to get access_token from Qu response.");
        })
        .to_string();

    qu_jwt
}

pub async fn menus(jwt: String) -> Menus {
    let url = format!("{}/sales/menus", get_qu_base_url());
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert(
        "Authorization",
        format!("Bearer {}", jwt)
            .parse()
            .expect("Failed to parse authorization header."),
    );
    headers.insert(
        "X-Integration",
        std::env::var("X_INTEGRATION")
            .expect("X_INTEGRATION environment variable not set")
            .parse()
            .expect("Failed to parse x-integration header."),
    );

    let params = [("LocationId", std::env::var("LOCATION_ID").expect("LOCATION_ID environment variable not set")), ("FulfillmentMethod", "1".to_string())];

    let client = reqwest::Client::new();
    let response = client
        .get(url)
        .headers(headers)
        .query(&params)
        .send()
        .await
        .expect("Failed to make HTTP request to Qu.");

    let response_text = response.text().await.expect("Failed to get response text");
    log::info!("Qu menu API response received successfully");
    
    let menus: Menus = serde_json::from_str(&response_text).expect("Failed to parse Qu response.");
    
    // Check if the response contains errors
    if let Some(errors) = &menus.errors {
        if let Some(succeed) = menus.succeed {
            if !succeed {
                log::error!("Qu API returned errors: {:?}", errors);
                for error in errors {
                    log::error!("Error {}: {} - {}", error.code, error.key, error.message);
                }
                panic!("Qu API returned errors. Check the logs for details.");
            }
        }
    }
    
    // Check if we have the expected value field
    if menus.value.is_none() {
        log::error!("Qu API response missing 'value' field. Full response: {}", response_text);
        panic!("Qu API response missing 'value' field.");
    }

    menus
}

pub async fn descendants(jwt: String, snapshot_id: String, item_path_key: String) -> Descendants {
    let url = format!("{}/sales/menus/{snapshot_id}/items/{item_path_key}/descendants", get_qu_base_url());
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert(
        "Authorization",
        format!("Bearer {}", jwt)
            .parse()
            .expect("Failed to parse authorization header."),
    );
    headers.insert(
        "X-Integration",
        std::env::var("X_INTEGRATION")
            .expect("X_INTEGRATION environment variable not set")
            .parse()
            .expect("Failed to parse x-integration header."),
    );

    let params = [("LocationId", std::env::var("LOCATION_ID").expect("LOCATION_ID environment variable not set")), ("FulfillmentMethod", "1".to_string())];

    let client = reqwest::Client::new();
    let response = client
        .get(url)
        .headers(headers)
        .query(&params)
        .send()
        .await
        .expect("Failed to make HTTP request to Qu.");

    let descendants: Descendants = response.json().await.expect("Failed to parse Qu response.");

    descendants
}

pub async fn orders(jwt: String, snapshot_id: String) -> Orders {
    let url = format!("{}/sales/orders", get_qu_base_url());
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert(
        "Authorization",
        format!("Bearer {}", jwt)
            .parse()
            .expect("Failed to parse authorization header."),
    );
    headers.insert(
        "X-Integration",
        std::env::var("X_INTEGRATION")
            .expect("X_INTEGRATION environment variable not set")
            .parse()
            .expect("Failed to parse x-integration header."),
    );
    headers.insert(
        "content-type",
        "application/json"
            .parse()
            .expect("Failed to parse x-integration header."),
    );

    let body = serde_json::json!({
        "menuSnapshotId": snapshot_id
    });

    let client = reqwest::Client::new();
    let response = client
        .post(url)
        .headers(headers)
        .json(&body)
        .send()
        .await
        .expect("Failed to make HTTP request to Qu.");

    let orders: Orders = response.json().await.expect("Failed to parse Qu response.");

    orders
}

pub async fn add_item(
    jwt: String,
    order_id: String,
    item_path_key: String,
) -> Result<String, String> {
    let url = format!("{}/sales/orders/{order_id}/items", get_qu_base_url());
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert(
        "Authorization",
        format!("Bearer {}", jwt)
            .parse()
            .expect("Failed to parse authorization header."),
    );
    headers.insert(
        "X-Integration",
        std::env::var("X_INTEGRATION")
            .expect("X_INTEGRATION environment variable not set")
            .parse()
            .expect("Failed to parse x-integration header."),
    );
    headers.insert(
        "content-type",
        "application/json"
            .parse()
            .expect("Failed to parse x-integration header."),
    );

    let body = serde_json::json!({
        "itemPathKey": item_path_key
    });

    let client = reqwest::Client::new();
    let response = client
        .post(url)
        .headers(headers)
        .json(&body)
        .send()
        .await
        .expect("Failed to make HTTP request to Qu.");

    if response.status().is_success() {
        Ok(response.text().await.expect("Failed to parse Qu response."))
    } else {
        let response_status = response.status();
        let response_text = response.text().await.expect("Failed to parse Qu response.");
        error!(
            "Failed to submit item {} to Qu: {:?} - {:?}",
            item_path_key, response_status, response_text
        );
        Err(response_text)
    }
}

pub async fn delete_item(jwt: String, order_id: String, item_id: String) -> String {
    let url = format!(
        "{}/sales/orders/{order_id}/items/{item_id}", get_qu_base_url()
    );
    dbg!(&url);
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert(
        "Authorization",
        format!("Bearer {}", jwt)
            .parse()
            .expect("Failed to parse authorization header."),
    );
    headers.insert(
        "X-Integration",
        std::env::var("X_INTEGRATION")
            .expect("X_INTEGRATION environment variable not set")
            .parse()
            .expect("Failed to parse x-integration header."),
    );

    dbg!(&headers);

    let client = reqwest::Client::new();
    let response = client
        .delete(url)
        .headers(headers)
        .send()
        .await
        .expect("Failed to make HTTP request to Qu.");

    response.text().await.expect("Failed to parse Qu response.")
}

pub async fn add_modifier(
    jwt: String,
    order_id: String,
    item_id: String,
    item_path_key: String,
) -> Result<String, String> {
    let url = format!(
        "{}/sales/orders/{order_id}/items/{item_id}/modifiers", get_qu_base_url()
    );
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert(
        "Authorization",
        format!("Bearer {}", jwt)
            .parse()
            .expect("Failed to parse authorization header."),
    );
    headers.insert(
        "X-Integration",
        std::env::var("X_INTEGRATION")
            .expect("X_INTEGRATION environment variable not set")
            .parse()
            .expect("Failed to parse x-integration header."),
    );
    headers.insert(
        "content-type",
        "application/json"
            .parse()
            .expect("Failed to parse x-integration header."),
    );

    let body = serde_json::json!([{
        "itemPathKey": item_path_key
    }]);

    let client = reqwest::Client::new();
    let response = client
        .post(url)
        .headers(headers)
        .json(&body)
        .send()
        .await
        .expect("Failed to make HTTP request to Qu.");

    if response.status().is_success() {
        Ok(response.text().await.expect("Failed to parse Qu response."))
    } else {
        let response_status = response.status();
        let response_text = response.text().await.expect("Failed to parse Qu response.");
        error!(
            "Failed to add modifier {} to item {}: {:?} - {:?}",
            item_path_key, item_id, response_status, response_text
        );
        Err(response_text)
    }
}

pub async fn order(jwt: String, order_id: String) -> String {
    let url = format!("{}/sales/orders/{order_id}", get_qu_base_url());
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert(
        "Authorization",
        format!("Bearer {}", jwt)
            .parse()
            .expect("Failed to parse authorization header."),
    );
    headers.insert(
        "X-Integration",
        std::env::var("X_INTEGRATION")
            .expect("X_INTEGRATION environment variable not set")
            .parse()
            .expect("Failed to parse x-integration header."),
    );

    let client = reqwest::Client::new();
    let response = client
        .get(url)
        .headers(headers)
        .send()
        .await
        .expect("Failed to make HTTP request to Qu.");

    response.text().await.expect("Failed to parse Qu response.")
}

pub async fn find_item(menus: &Menus, item_path_key: String) -> Option<Item> {
    for category in &menus.value.as_ref().unwrap().categories {
        for item in &category.children {
            if item_path_key == item.item_path_key {
                return Some(item.clone());
            }
        }
    }
    None
}

pub async fn find_modifier(
    modifiers: &HashMap<String, Descendants>,
    item_path_key: String,
) -> Option<Item> {
    for descendants in modifiers.values() {
        for item in &descendants.value {
            let mut stack = VecDeque::new();

            stack.push_back(item.clone());

            while let Some(item) = stack.pop_front() {
                if item_path_key == item.item_path_key {
                    return Some(item.clone());
                }

                for child in &item.children {
                    stack.push_back(child.clone());
                }
            }
        }
    }
    None
}
