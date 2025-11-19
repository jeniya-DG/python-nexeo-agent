use log::info;

use crate::qu;

pub async fn persist_order(
    qu_jwt: String,
    qu_order_id: Option<String>,
    dg_request_id: Option<String>,
    reason: String,
) {
    let orders_directory =
        std::env::var("ORDERS_DIRECTORY").unwrap_or("/home/nikola/orders".to_string());

    if let (Some(qu_order_id), Some(dg_request_id)) = (qu_order_id.clone(), dg_request_id) {
        let timestamp = chrono::Utc::now().to_rfc3339();
        let key = format!(
            "{}_{}_{}_{}.json",
            timestamp, qu_order_id, dg_request_id, reason
        );

        let order = qu::order(qu_jwt.clone(), qu_order_id.clone()).await;

        let path = format!("{}/{}", orders_directory, key);
        let file = std::fs::File::create(&path).expect("Unable to create file for qu order.");

        serde_json::to_writer_pretty(file, &order).expect("Unable to write file for order.");

        info!("Persisted {key} with contents: {order}");
    }
}
