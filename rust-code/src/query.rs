use std::collections::HashMap;
use std::collections::VecDeque;
use std::sync::Arc;

use log::info;
use qdrant_client::qdrant::{
    Condition, CreateCollectionBuilder, Distance, Filter, PointId, PointStruct,
    SearchPointsBuilder, SearchResponse, UpsertPointsBuilder, VectorParamsBuilder, Vectors,
};
use qdrant_client::{Payload, Qdrant};
use rust_bert::pipelines::sentence_embeddings::{
    SentenceEmbeddingsBuilder, SentenceEmbeddingsModel, SentenceEmbeddingsModelType,
};
use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;

use crate::qu::{Descendants, Item, Menus};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryPayload {
    pub item_path_key: String,
    /// A vector of all parent path keys.
    /// E.g.if the `item_path_key` is `"47587-56635-122228"`
    /// then `parent_path_keys` should be `["47587", "47587-56635"]`.
    /// This is redundant but it is the only way to get qdrant to filter
    /// by parents of parents / grandparents / etc.
    pub parent_path_keys: Vec<String>,
    pub title: String,
    pub description: String,
}

impl Into<Payload> for QueryPayload {
    fn into(self) -> Payload {
        let mut map: HashMap<String, qdrant_client::qdrant::Value> = HashMap::new();
        map.insert("item_path_key".to_string(), self.item_path_key.into());
        map.insert("parent_path_keys".to_string(), self.parent_path_keys.into());
        map.insert("title".to_string(), self.title.into());
        map.insert("description".to_string(), self.description.into());
        Payload::from(map)
    }
}

impl TryFrom<HashMap<String, qdrant_client::qdrant::Value>> for QueryPayload {
    type Error = String;

    fn try_from(map: HashMap<String, qdrant_client::qdrant::Value>) -> Result<Self, Self::Error> {
        let item_path_key = map
            .get("item_path_key")
            .and_then(|v| v.as_str())
            .ok_or_else(|| "Missing or invalid 'item_path_key' field!".to_string())?
            .to_string();

        let parent_path_keys = map
            .get("parent_path_keys")
            .and_then(|v| v.as_list())
            .ok_or_else(|| "Missing or invalid 'parent_path_keys' field!".to_string())?;

        let parent_path_keys = parent_path_keys
            .iter()
            .map(|v| {
                v.as_str()
                    .expect("Failed to parse parent path key.")
                    .to_string()
            })
            .collect();

        let title = map
            .get("title")
            .and_then(|v| v.as_str())
            .ok_or_else(|| "Missing or invalid 'title' field!".to_string())?
            .to_string();

        let description = map
            .get("description")
            .and_then(|v| v.as_str())
            .ok_or_else(|| "Missing or invalid 'description' field!".to_string())?
            .to_string();

        Ok(QueryPayload {
            item_path_key,
            parent_path_keys,
            title,
            description,
        })
    }
}

pub async fn model() -> SentenceEmbeddingsModel {
    let model = tokio::task::spawn_blocking(|| {
        SentenceEmbeddingsBuilder::remote(SentenceEmbeddingsModelType::AllMiniLmL6V2).create_model()
    })
    .await
    .expect("Failed to initialize the embeddings model.")
    .expect("Failed to initialize the embeddings model.");

    model
}

pub async fn qdrant(
    menu: &Menus,
    modifiers: &HashMap<String, Descendants>,
    model: &SentenceEmbeddingsModel,
) -> Qdrant {
    let qdrant_url =
        std::env::var("QDRANT_URL").unwrap_or_else(|_| "http://localhost:6334".to_string());
    let qdrant = Qdrant::from_url(&qdrant_url)
        .build()
        .expect("Failed to connect to the qdrant server.");

    let collections = qdrant
        .list_collections()
        .await
        .expect("Failed to get a list of existing collections.");

    if !collections
        .collections
        .iter()
        .any(|collection_description| collection_description.name == "menu")
    {
        qdrant
            .create_collection(
                CreateCollectionBuilder::new("menu")
                    .vectors_config(VectorParamsBuilder::new(384, Distance::Cosine)),
            )
            .await
            .expect("Failed to create new collection.");

        for category in menu.value.as_ref().unwrap().categories.iter() {
            for item in &category.children {
                add_point(item.clone(), model, &qdrant, "menu").await;
            }
        }
    }

    if !collections
        .collections
        .iter()
        .any(|collection_description| collection_description.name == "modifiers")
    {
        qdrant
            .create_collection(
                CreateCollectionBuilder::new("modifiers")
                    .vectors_config(VectorParamsBuilder::new(384, Distance::Cosine)),
            )
            .await
            .expect("Failed to create new collection.");

        let mut total = 0;
        for descendants in modifiers.values() {
            for item in &descendants.value {
                total += count_children(item.clone()) + 1;
            }
        }

        let mut count = 0;
        for descendants in modifiers.values() {
            for item in &descendants.value {
                count +=
                    add_points_pseudo_recursive(item.clone(), model, &qdrant, "modifiers").await;

                if count % 500 == 0 || count == total {
                    info!("Added {count} out of {total} modifiers to the vector database.");
                }
            }
        }
    }

    qdrant
}

fn count_children(item: Item) -> u64 {
    let mut stack = VecDeque::new();

    stack.push_back(item.clone());

    let mut count = 0;
    while let Some(item) = stack.pop_front() {
        count += 1;

        for child in &item.children {
            stack.push_back(child.clone());
        }
    }

    // technically `count_children` should count children, which doesn't
    // include the parent item, but the code is simpler if the parent item
    // is included in the `VecDeque` - so here we simply compensate
    if count > 0 {
        count -= 1;
    }

    count
}

async fn add_points_pseudo_recursive(
    item: Item,
    model: &SentenceEmbeddingsModel,
    qdrant: &Qdrant,
    collection: &str,
) -> u64 {
    let mut stack = VecDeque::new();

    stack.push_back(item.clone());

    let mut count = 0;
    while let Some(item) = stack.pop_front() {
        add_point(item.clone(), model, qdrant, collection).await;
        count += 1;

        for child in &item.children {
            stack.push_back(child.clone());
        }
    }

    count
}

pub async fn add_point(
    item: Item,
    model: &SentenceEmbeddingsModel,
    qdrant: &Qdrant,
    collection: &str,
) {
    let id = item.query_id.to_string();
    let item_path_key = item.item_path_key.clone();
    let title = item.title.clone();
    let description = item.display_attribute.description.unwrap_or_default();

    let mut text = format!("{}", title);
    if !description.is_empty() {
        text = format!("{} - {}", text, description);
    }
    let embedding = model
        .encode(&[text])
        .expect("Failed to encode item embedding.");
    let embedding = embedding
        .get(0)
        .expect("Failed to get item embeddings.")
        .clone();

    // turns an item path key like "47587-56635-122228"
    // into a vector of parent path keys like ["47587", "47587-56635"]
    // for clarity, I could make this a function on `QueryPayload` I suppose
    let parent_path_keys: Vec<String> = item_path_key
        .split('-')
        .scan(Vec::new(), |accumulated, part| {
            if accumulated.is_empty() {
                accumulated.push(part.to_string());
            } else {
                accumulated.push(format!("{}-{}", accumulated.last().unwrap(), part));
            }
            Some(accumulated.last().unwrap().clone())
        })
        .collect();

    let payload = QueryPayload {
        item_path_key,
        parent_path_keys,
        title,
        description,
    };
    let payload: Payload = payload.into();

    let point = PointStruct::new(id, Vectors::from(embedding.clone()), payload);

    qdrant
        .upsert_points(UpsertPointsBuilder::new(collection, vec![point]))
        .await
        .expect("Failed to upsert points.");
}

pub async fn query_qdrant(
    query: String,
    limit: Option<u64>,
    parent: Option<String>,
    model: Arc<Mutex<SentenceEmbeddingsModel>>,
    qdrant: &Qdrant,
    collection: &str,
) -> SearchResponse {
    info!("Performing query on: {query}.");

    let limit = limit.unwrap_or(5);

    let model = model.lock().await;

    let query_embedding = model
        .encode(&[query.trim()])
        .expect("Failed to generate embeddings for query.");

    let query_vector = query_embedding
        .get(0)
        .expect("No embedding returned.")
        .clone();

    let filter = parent
        .map(|parent| Filter::must(vec![Condition::matches("parent_path_keys", vec![parent])]));

    let mut builder = SearchPointsBuilder::new(collection, query_vector, limit).with_payload(true);

    if let Some(filter) = filter {
        builder = builder.filter(filter);
    }

    let builder = builder.build();

    let search_response = qdrant
        .search_points(builder)
        .await
        .expect("Failed to query.");

    search_response
}

pub async fn query_menu(
    query: String,
    limit: Option<u64>,
    model: Arc<Mutex<SentenceEmbeddingsModel>>,
    qdrant: &Qdrant,
    qu_menu: Menus,
) -> Vec<Item> {
    let search_response = query_qdrant(query, limit, None, model, qdrant, "menu").await;

    let mut items = Vec::new();

    for point in search_response.result {
        let id = point.id;

        if let Some(item) = find_item(&qu_menu, id).await {
            items.push(item);
        }
    }

    items
}

pub async fn find_item(menu: &Menus, id: Option<PointId>) -> Option<Item> {
    for category in &menu.value.as_ref().unwrap().categories {
        for item in &category.children {
            if let Some(ref id) = id {
                if let Some(id) = &id.point_id_options {
                    if let qdrant_client::qdrant::point_id::PointIdOptions::Uuid(id) = id {
                        if *id == item.query_id.to_string() {
                            return Some(item.clone());
                        }
                    }
                }
            }
        }
    }
    None
}

pub async fn query_modifiers(
    query: String,
    limit: Option<u64>,
    parent: Option<String>,
    model: Arc<Mutex<SentenceEmbeddingsModel>>,
    qdrant: &Qdrant,
    qu_modifiers: HashMap<String, Descendants>,
) -> Vec<Item> {
    let search_response = query_qdrant(query, limit, parent, model, qdrant, "modifiers").await;

    let mut items = Vec::new();

    for point in search_response.result {
        let id = point.id;

        if let Some(item) = find_modifier(&qu_modifiers, id).await {
            items.push(item);
        }
    }

    items
}

pub async fn find_modifier(
    modifiers: &HashMap<String, Descendants>,
    id: Option<PointId>,
) -> Option<Item> {
    for descendants in modifiers.values() {
        for item in &descendants.value {
            let mut stack = VecDeque::new();

            stack.push_back(item.clone());

            while let Some(item) = stack.pop_front() {
                if let Some(ref id) = id {
                    if let Some(id) = &id.point_id_options {
                        if let qdrant_client::qdrant::point_id::PointIdOptions::Uuid(id) = id {
                            if *id == item.query_id.to_string() {
                                return Some(item.clone());
                            }
                        }
                    }
                }

                for child in &item.children {
                    stack.push_back(child.clone());
                }
            }
        }
    }
    None
}
