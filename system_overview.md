# Jack in the Box Voice Agent - System Overview

Voice ordering system integrating Deepgram's Voice Agent API, Qu API, and semantic menu search.

---

## Architecture Diagram

```
Browser Client
     |
     | WebSocket + Audio
     v
Python Web Server (FastAPI)
     |
     |-- Deepgram Agent API (Voice I/O + LLM)
     |
     |-- Rust Backend (Semantic Search)
     |        |
     |        |-- Qdrant (Vector Database)
     |        |
     |        |-- Qu API (Menu Data Source)
     |
     |-- qu_prices_complete.json (86,115 prices from Qu API)
     |
     |-- Qu API (Order Submission)
```

---

## Top-Level Python Files

### 1. `web_voice_agent_server.py`
**Primary application server**

- FastAPI web server hosting the voice agent UI
- WebSocket relay between browser and Deepgram Agent API
- Handles bidirectional audio streaming (browser <-> Deepgram)
- Processes function call requests from Deepgram agent
- Serves static files (HTML, favicon)
- Endpoint: `/ws` for WebSocket, `/menu` for menu data
- Port: 8000

Key responsibilities:
- Accept browser WebSocket connections
- Forward audio to Deepgram, receive audio back
- Execute function calls (query_items, add_item, etc.)
- Send function results back to Deepgram
- Manage conversation lifecycle (start/end logging)

### 2. `jitb_functions.py`
**Business logic and function implementations**

Core module containing all function handlers that the Deepgram agent calls.

Functions:
- `query_items()` - Search menu items via Rust backend
- `query_modifiers()` - Search modifiers for a parent item
- `add_item()` - Add item to current order
- `add_modifier()` - Add modifier to an item (handles combo pricing)
- `delete_item()` - Remove item from order
- `submit_order_to_qu()` - Log order (Qu submission incomplete)
- `get_menu_categories()` - Return cached menu categories
- `get_category_items()` - Return items for a specific category

Additional functionality:
- Load and cache menu data at startup
- Load 86,115 real Qu prices from `qu_prices_complete.json`
  - This JSON is generated whenever menu is loaded from Qu (via `get_full_menu_with_prices.py`)
- Calculate order totals (with combo modifier logic)
- Manage current order state
- Generate conversation logs with timestamps

### 3. `agent_config.py`
**Deepgram agent configuration**

Defines the agent's behavior, personality, and function schemas.

Contains:
- Agent settings (TTS model, STT model, LLM model, temperature)
- System prompt with ordering rules and personality
- Function definitions (JSON schema for each function)
- Critical rules for combo handling and modifier logic
- Sample rates for audio I/O

Key rules enforced:
- Always ask for side/drink when combo is ordered
- Use `query_modifiers` (not `query_items`) for combo components
- Use first result from search queries
- Replace modifiers (don't delete entire item)
- Specific handling for Coca-Cola vs flavor shots



### 4. `get_full_menu_with_prices.py`
**Qu API price fetching script**

Fetches current prices from Qu API and generates the price lookup file.

Process:
1. Authenticate with Qu API (OAuth2 JWT)
2. Get location context (OrderChannelId, OrderTypeId) from `/api/v4/locations/{locationId}`
3. Fetch full menu from `/api/v4/menus` (includes priceAttribute for all items)
4. Recursively traverse menu tree to extract prices
5. Save flattened price map to `qu_prices_complete.json`

Output format:
```json
{
  "extracted_at": "2025-11-18T21:30:00",
  "source": "/api/v4/menus (Full Menu with Dynamic Context)",
  "location_id": "4776",
  "price_count": 86115,
  "prices": {
    "47587-56634-105606": 8.19,
    "47587-56634-47679": 5.49,
    ...
  }
}
```

Key features:
- Fetches 86,115 prices covering all menu items and modifiers
- Prices stored as floats for O(1) lookup by itemPathKey
- Menu response is ~137MB (takes 5-10 seconds to download)
- Runs automatically as part of nightly refresh
- Can be run manually anytime for immediate price updates

Usage:
```bash
python3 get_full_menu_with_prices.py
```


### 5. `latency_tracker.py`
**Performance monitoring utility**

Tracks execution time for various operations.

Tracks:
- Deepgram agent response time
- Function call execution time
- Rust backend query latency
- User speech duration

Output: `latency_logs.txt` with timestamped measurements

Format: `TIMESTAMP | LATENCY | operation_name | duration_ms | metadata`
---

## Shell Scripts

### 1. `refresh_qu_nightly.sh`
**Automated nightly menu and price refresh (EC2 only)**

Purpose: Ensure menu data and prices are current by re-indexing from Qu API daily

Actions:
1. Stop Rust backend and Qdrant containers
2. Clear Qdrant storage (force fresh index)
3. Restart Qdrant container
4. Restart Rust backend (triggers menu fetch + index)
5. Verify indexing completed successfully
6. **Refresh prices from Qu API** (via `get_full_menu_with_prices.py`)
7. Verify `qu_prices_complete.json` was updated
8. Log all actions to `qu_refresh.log`

What gets refreshed:
- Menu structure (615 items) → Rust backend + Qdrant
- Modifiers (54,000+) → Rust backend + Qdrant
- Prices (86,115) → Python script → `qu_prices_complete.json`



### 2. `restart-qu.sh`
**Manual Qu backend restart with fresh indexing**

Purpose: Manually restart Qdrant and Rust backend when needed

Actions:
1. Stop and remove Qdrant and Rust containers
2. Remove Qdrant storage directory
3. Start Qdrant in a `screen` session
4. Start Rust backend in a `screen` session
5. Wait for indexing to complete

Use cases:
- Troubleshooting search issues
- Testing menu changes
- After Qu API updates
- Manual refresh outside scheduled time

Can be used on both local and EC2 (paths differ)

### 3. `restart_all_services_ec2.sh`
**Remote restart of all EC2 services**

Purpose: Restart entire stack on EC2 from your local machine

Actions:
1. SSH to EC2
2. Stop Python web service (systemd)
3. Stop Rust backend and Qdrant (podman)
4. Restart Qdrant
5. Wait for Qdrant to be ready
6. Restart Rust backend with menu indexing
7. Wait for indexing to complete
8. Restart Python web service
9. Verify all services are running

Usage: `./restart_all_services_ec2.sh` (from local machine)

### 4. `setup_nightly_refresh.sh`
**One-time setup for nightly refresh cron job**

Purpose: Deploy and configure automated nightly refresh on EC2

Actions:
1. Copy `refresh_qu_nightly.sh` to EC2
2. Make script executable
3. Install cron job (4:00 AM daily)
4. Display verification commands

Usage: Run once during initial EC2 setup or after cron changes

---

## Rust Backend (`rust-code/`)

### Purpose
High-performance semantic search service that converts menu items and modifiers into vector embeddings for natural language search.

### Architecture Overview

The Rust backend acts as a bridge between:
1. Qu API (menu data source)
2. Qdrant (vector database for semantic search)
3. Python server (query interface)

It performs two critical tasks:
- **Indexing**: Convert menu text into 384-dimensional vectors
- **Querying**: Find semantically similar items using cosine similarity

---

### Key Components

#### 1. `src/main.rs` - Application Entry Point

**Startup sequence** (4 phases):

**Phase 1: Authentication**
```rust
let qu_jwt = qu::jwt(qu_secret).await;
```
- Obtains OAuth2 JWT token from Qu API
- Uses `CLIENT_ID` and `QU_SECRET` environment variables
- Token valid for 3600 seconds
- Endpoint: `POST /authentication/oauth2/access-token`

**Phase 2: Menu Loading**
```rust
let qu_menu = if cached { load_from_disk() } else { fetch_from_qu() };
```
- Checks for cached menu at `./menu/menu.json`
- If not cached: Fetches from Qu API via `GET /api/v4/sales/menus`
- Saves to disk for faster subsequent startups
- Parses hierarchical structure: Categories → Items
- Result: ~615 top-level menu items

Menu structure example:
```json
{
  "snapshotId": "690142b50a47ca19cd06b82c",
  "categories": [
    {
      "title": "Lunch/Dinner",
      "itemPathKey": "47587-56634",
      "children": [
        {
          "title": "Combo - Jumbo Jack",
          "itemPathKey": "47587-56634-105606",
          "displayAttribute": {
            "description": "100% beef seasoned as it grills..."
          }
        }
      ]
    }
  ]
}
```

**Phase 3: Modifiers Loading**
```rust
for item in items {
    let descendants = qu::descendants(jwt, snapshot_id, item_path_key).await;
    qu_modifiers.insert(item_path_key, descendants);
}
```
- Checks for cached modifiers at `./menu/modifiers.json`
- If not cached: Fetches descendants for EACH menu item
- Endpoint: `GET /api/v4/menus/{menuId}/descendants/{itemPathKey}`
- Progress logged: "Progress: 45% (36/80 categories processed)"
- Result: ~54,000 modifiers (sides, drinks, toppings, sizes, etc.)

Why descendants endpoint?
- Main menu only shows top-level items
- Modifiers are nested deep in the hierarchy
- Each item (especially combos) has many child modifiers
- Example: Jumbo Jack combo → Fries (regular/curly/wedges) → Drinks (20+ options)

**Phase 4: Vectorization**
```rust
let query_model = query::model().await;
let query_qdrant = query::qdrant(&qu_menu, &qu_modifiers, &query_model).await;
```
- Initializes sentence transformer model
- Creates/connects to Qdrant collections
- Generates embeddings for all items and modifiers
- Indexes into vector database

**HTTP Server**
- Framework: Axum (async Rust web framework)
- Port: 4000 (configurable via `PORT` env var)
- Endpoints:
  - `GET /menu` - Return full cached menu (no vectors)
  - `POST /query/items` - Semantic search menu items
  - `POST /query/modifiers` - Semantic search modifiers

**App State**
```rust
struct AppState {
    qu_jwt: String,                    // Cached JWT token
    qu_menu: Menus,                    // Full menu structure
    qu_modifiers: HashMap<String, Descendants>,  // All modifiers
    query_model: SentenceEmbeddingsModel,        // Embeddings generator
    query_qdrant: Qdrant,              // Vector DB client
}
```

---

#### 2. `src/qu.rs` - Qu API Integration

**Data Structures**

Defines Rust structs matching Qu API JSON responses:
```rust
struct Menus {
    value: Option<MenusValue>,
    succeed: Option<bool>,
    errors: Option<Vec<QuError>>,
}

struct Item {
    title: String,              // "Combo - Jumbo Jack"
    item_path_key: String,      // "47587-56634-105606"
    parent_path_key: String,    // "47587-56634"
    display_attribute: DisplayAttribute,
    children: Vec<Item>,        // Nested modifiers
    query_id: Uuid,            // Generated for Qdrant indexing
}
```

**Functions**

**`jwt(secret: String) -> String`**
- OAuth2 client credentials flow
- Body: `grant_type=client_credentials&client_id=X&client_secret=Y&scope=menu:* order:*`
- Returns: JWT token string
- Caches in `AppState` for all API calls

**`menus(jwt: String) -> Menus`**
- Fetches main menu structure
- Headers: `Authorization: Bearer {jwt}`, `Company-Id: 405`, `Location-Id: 4776`
- Returns: Hierarchical menu with categories and top-level items
- Does NOT include all modifiers (hence descendants call needed)

**`descendants(jwt: String, menu_id: String, item_path_key: String) -> Descendants`**
- Fetches ALL possible modifiers/options for a specific item
- Example: For "Combo - Jumbo Jack" (itemPathKey: 47587-56634-105606):
  - Returns ~200 modifiers
  - Includes: Fries options, drink options, sizes, add-ons, etc.
- This is called 615 times (once per menu item) during startup
- Takes 30-60 seconds to complete all calls
- Results cached to avoid repeating on next startup

---

#### 3. `src/query.rs` - Vectorization Engine

**Sentence Transformers**

Model: `all-MiniLM-L6-v2`
- Pre-trained transformer model from HuggingFace
- Converts text to 384-dimensional dense vectors
- Optimized for semantic similarity tasks
- Fast inference: ~50ms per item

**Initialization**
```rust
pub async fn model() -> SentenceEmbeddingsModel {
    SentenceEmbeddingsBuilder::remote(
        SentenceEmbeddingsModelType::AllMiniLmL6V2
    )
    .create_model()
}
```
- Downloads model weights from HuggingFace on first run
- Caches locally: `~/.cache/huggingface/` or `HF_HOME`
- Model size: ~90MB
- Loading time: 5-10 seconds

**Qdrant Connection**
```rust
let qdrant = Qdrant::from_url("http://localhost:6334")
    .build()
    .expect("Failed to connect to Qdrant");
```
- Connects via gRPC (port 6334, not HTTP 6333)
- gRPC is faster than HTTP for high-throughput operations
- Maintains persistent connection for batch operations

**Collection Creation**

Two collections are created if they don't exist:

**`menu` collection:**
```rust
qdrant.create_collection(
    CreateCollectionBuilder::new("menu")
        .vectors_config(VectorParamsBuilder::new(384, Distance::Cosine))
)
```
- Vector dimension: 384 (matches sentence transformer output)
- Distance metric: Cosine similarity (range: -1 to 1)
- Why cosine? Best for semantic similarity of text embeddings

**`modifiers` collection:**
- Same configuration as `menu`
- Separate collection for faster filtering

**Vectorization Process**

For each menu item and modifier:

1. **Text Preparation**
```rust
let text = format!("{} - {}", title, description);
// Example: "Combo - Jumbo Jack - 100% beef seasoned as it grills, lettuce, tomato..."
```

2. **Embedding Generation**
```rust
let embedding = model.encode(&[text])?;
// Input:  "Combo - Jumbo Jack - 100% beef..."
// Output: [0.0234, -0.1456, 0.3421, ..., 0.0891]  (384 floats)
```

3. **Parent Path Keys Extraction**
```rust
let parent_path_keys = "47587-56634-105606"
    .split('-')
    .scan(Vec::new(), |acc, part| {
        // Result: ["47587", "47587-56634"]
    })
```
Why? Enables filtering modifiers by parent item:
- Query: "Find modifiers for Jumbo Jack combo"
- Filter: `parent_path_keys contains "47587-56634-105606"`
- Result: Only modifiers belonging to this specific combo

4. **Payload Construction**
```rust
struct QueryPayload {
    item_path_key: String,      // Unique ID
    parent_path_keys: Vec<String>,  // For filtering
    title: String,              // Display name
    description: String,        // Full text
}
```

5. **Point Insertion**
```rust
qdrant.upsert_points(
    UpsertPointsBuilder::new(collection, vec![
        PointStruct::new(
            id,                 // UUID
            embedding,          // 384-dimensional vector
            payload.into()      // Metadata
        )
    ])
)
```

**Batch Indexing**

Items indexed sequentially:
```rust
for category in menu.categories {
    for item in category.children {
        add_point(item, model, qdrant, "menu").await;
    }
}
```

Modifiers indexed with progress tracking:
```rust
let total = count_all_modifiers(modifiers);
let mut count = 0;
for descendants in modifiers.values() {
    for item in descendants.value {
        add_points_recursive(item, model, qdrant, "modifiers").await;
        count += 1;
        if count % 500 == 0 {
            info!("Added {count}/{total} modifiers");
        }
    }
}
```

Progress output:
```
Added 500 out of 54124 modifiers to the vector database.
Added 1000 out of 54124 modifiers to the vector database.
...
Added 54124 out of 54124 modifiers to the vector database.
```

**Recursive Modifier Handling**

Modifiers have nested children (e.g., Drink → Size → Flavor):
```rust
async fn add_points_pseudo_recursive(item: Item, ...) {
    let mut stack = VecDeque::new();
    stack.push_back(item);
    
    while let Some(item) = stack.pop_front() {
        add_point(item.clone(), model, qdrant, collection).await;
        
        for child in item.children {
            stack.push_back(child);  // Process children
        }
    }
}
```

Uses iterative approach (stack-based) instead of true recursion to avoid stack overflow with deep nesting.

---

#### 4. `src/handlers/http.rs` - Query Endpoints

**`POST /query/items`**

Request body:
```json
{
  "query": "jumbo jack",
  "limit": 5
}
```

Process:
1. Generate embedding for query text
```rust
let query_embedding = model.encode(&["jumbo jack"])?;
```

2. Search Qdrant
```rust
let response = qdrant.search_points(
    SearchPointsBuilder::new("menu", query_embedding, limit)
).await?;
```

3. Return results ranked by similarity
```json
{
  "items": [
    {
      "title": "Combo - Jumbo Jack",
      "itemPathKey": "47587-56634-105606",
      "score": 0.89,  // Cosine similarity
      "queryId": "uuid..."
    },
    {
      "title": "Burger - Jumbo Jack",
      "itemPathKey": "47587-56634-47679",
      "score": 0.85,
      ...
    }
  ]
}
```

**`POST /query/modifiers`**

Request body:
```json
{
  "query": "curly fries",
  "parent": "47587-56634-105606",  // Filter by parent item
  "limit": 5
}
```

Process:
1. Generate query embedding
2. Search with filter:
```rust
let filter = Filter::must(vec![
    Condition::matches("parent_path_keys", parent_item_path_key)
]);

qdrant.search_points(
    SearchPointsBuilder::new("modifiers", query_embedding, limit)
        .filter(filter)
).await?;
```

This ensures results are ONLY modifiers that belong to the parent item.

---

## Qdrant Vector Database

### Purpose
Store and search menu items/modifiers using semantic similarity.

### Collections

#### `menu` collection
- **Points**: ~615 menu items
- **Vector dimension**: 384 (from sentence transformer)
- **Payload**: itemPathKey, title, description, category

#### `modifiers` collection
- **Points**: ~54,000 modifiers
- **Vector dimension**: 384
- **Payload**: itemPathKey, name, parentPathKey, modifierType

### Why Qdrant?
- Fast semantic search (cosine similarity)
- Better than keyword matching for natural language queries
- Handles typos and variations ("jumbo jack" vs "jumbojack")
- Returns ranked results by relevance

### Ports
- **HTTP**: 6333 (API endpoints, admin UI)
- **gRPC**: 6334 (used by Rust backend for performance)

### Storage
- Local: `~/Desktop/CODE/JITB/dg-compat-lab/qdrant_storage/`
- EC2: `~/dg-compat-lab/qdrant_storage/`

### Refresh Strategy
Clear storage and re-index nightly to ensure current menu data.

---

## Qu POS API

### Purpose
Cloud-based POS system providing menu data and order submission.

### Authentication
OAuth2 client credentials flow

Required:
- `CLIENT_ID`: (stored in `.env`)
- `CLIENT_SECRET`: (stored in `.env`)
- `LOCATION_ID`: (stored in `.env`) 
- Scopes: `menu:* order:*`

Token expiry: 3600 seconds (refresh before expiry)

### Endpoints Used

#### Menu Endpoints
- `GET /api/v4/sales/menus` - Current menu with prices
- `GET /api/v4/menus/{menuId}/descendants` - Item modifiers

#### Order Endpoints (Incomplete Implementation)
- `POST /api/v4/sales/orders` - Create new order
- `POST /api/v4/sales/orders/{orderId}/bulk-items` - Add items
- `POST /api/v4/sales/orders/{orderId}/items/{itemId}/modifiers` - Add modifiers
- `POST /api/v4/sales/orders/{orderId}/payments` - Add payment (FAILING)
- `POST /api/v4/sales/orders/{orderId}/close-requests` - Close order (NOT REACHED)

Current status: Orders can be created and items added, but payment fails.
See `QU_ORDER_SUBMISSION_ISSUE.txt` for details.

### Headers Required
- `Authorization: Bearer {jwt_token}`
- `Company-Id: 405`
- `Location-Id: 4776`
- `X-Integration: 682c4b47f7e426d4b8208962`

### Menu Structure
Hierarchical: Category > Subcategory > Item > Modifier

Key identifiers:
- `itemPathKey`: Unique identifier for items/modifiers (e.g., "47587-56634-105606")
- `menuSnapshotId`: Version identifier for menu (changes when menu updates)

---


## Performance Characteristics

### Typical Latencies
- **Deepgram Agent Response**: 1-3 seconds (speech -> TTS)
- **Rust Backend Query**: 50-150ms (semantic search)
- **Function Execution**: 10-50ms (local operations)
- **Qu API Call**: 200-500ms (JWT fetch, menu query)

### Resource Usage
- **Qdrant**: ~200MB RAM (indexed data)
- **Rust Backend**: ~100MB RAM (embeddings + HTTP server)
- **Python Server**: ~80MB RAM (FastAPI + dependencies)

### Scalability
Current bottleneck: Deepgram Agent API (1 conversation per connection)
Can handle: Multiple concurrent conversations (separate WebSocket connections)

---

## Configuration Files

### `.env` Files (2 locations)

**Important**: There are TWO `.env` files in this project:

1. **Root `.env`** (`/dg-compat-lab/.env`)
   - Used by: Python web server
   - Loaded by: `python-dotenv` library
   - Location: Project root directory

2. **Rust `.env`** (`/dg-compat-lab/rust-code/.env`)
   - Used by: Rust backend
   - Loaded by: `run.sh` script (via `source`)
   - Location: `rust-code/` subdirectory

**Why two files?**
- Python and Rust load environment variables differently
- Allows separate configuration when needed
- Most variables should be identical in both files

**Required variables (must be in BOTH files):**
- `DEEPGRAM_API_KEY` - Deepgram authentication
- `CLIENT_ID` - Qu API authentication (Rust expects `CLIENT_ID`, Python can use either)
- `QU_SECRET` - Qu API secret
- `QU_BASE_URL` - Qu API endpoint
- `COMPANY_ID` - Qu company identifier
- `LOCATION_ID` - Qu location (4776)
- `QDRANT_URL` - Qdrant connection (http://localhost:6334)
- `USE_VECTOR` - Enable vector embeddings (1)

### `requirements.txt`

Python dependencies

Key packages:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `websockets` - WebSocket client
- `requests` - HTTP client
- `python-dotenv` - Environment variables
- `deepgram-sdk` - Deepgram client (optional, not currently used)

### `rust-code/Cargo.toml`
Rust dependencies

Key packages:
- `axum` - HTTP framework
- `qdrant-client` - Vector DB client
- `tch` - PyTorch bindings (embeddings)
- `rust-bert` - Transformer models
- `tokio` - Async runtime
- `serde` - JSON serialization

### `qu_prices_complete.json`

**Price lookup data file**

Generated by: `get_full_menu_with_prices.py`
Source: Qu API `/api/v4/menus` endpoint
Format: JSON object mapping itemPathKey to price (float)

Structure:
```json
{
  "extracted_at": "2025-11-18T21:30:00.123456",
  "source": "/api/v4/menus (Full Menu with Dynamic Context)",
  "location_id": "4776",
  "price_count": 86115,
  "prices": {
    "itemPathKey": price,
    ...
  }
}
```

Details:
- 86,115 price entries covering all menu items and modifiers
- Prices stored as floats for fast O(1) lookup
- Refreshed nightly at 4:00 AM via `refresh_qu_nightly.sh`
- Loaded at Python server startup by `jitb_functions.py`
- Used by `get_price_by_item_path_key()` for all price lookups

Manual refresh:
```bash
python3 get_full_menu_with_prices.py
```

---

## Troubleshooting Quick Reference

### Rust Backend Not Starting
1. Check Qdrant is running: `podman ps | grep qdrant`
2. Check port 4000: `lsof -i :4000`
3. Check environment variables in `.env`
4. Check LibTorch installation: `echo $LIBTORCH`

### Empty Query Results
1. Verify Qdrant has data: `curl http://localhost:6333/collections/menu`
2. Check `USE_VECTOR=1` in `.env`
3. Restart Rust backend to re-index

### Order Total Mismatch
1. Check conversation log: `conversation_logs/conversation_*.log`
2. Check Python logs: `journalctl -u jitb-web` (EC2) or terminal output (local)
3. Verify price file loaded: Look for "Loaded 86115 real Qu prices" in logs
4. Check if prices are stale: `cat qu_prices_complete.json | grep extracted_at`
5. Manually refresh prices: `python3 get_full_menu_with_prices.py`

### WebSocket Connection Failed
1. Check Python server is running: `curl http://localhost:8000`
2. Check Deepgram API key is valid
3. Check browser console for errors
4. Verify microphone permissions granted

---

## Deployment Locations

### Local Development
- **Python**: `~/Desktop/CODE/JITB/dg-compat-lab/`
- **Rust**: `~/Desktop/CODE/JITB/dg-compat-lab/rust-code/`
- **Qdrant Storage**: `~/Desktop/CODE/JITB/dg-compat-lab/qdrant_storage/`
- **URL**: http://localhost:8000

### EC2 Production
- **Python**: `/home/ubuntu/dg-compat-lab/`
- **Rust**: `/home/ubuntu/dg-compat-lab/rust-code/`
- **Qdrant Storage**: `/home/ubuntu/dg-compat-lab/qdrant_storage/`
- **Service**: `systemd` (jitb-web.service)
- **URL**: https://jitb.deepgram.com

### Service Management (EC2)
- **Python**: `sudo systemctl {start|stop|restart|status} jitb-web`
- **Rust**: `podman {start|stop} nexeo-sts`
- **Qdrant**: `podman {start|stop} qdrant`
- **Logs**: `sudo journalctl -u jitb-web -f`

---

## Future Improvements


1. Complete Qu order submission (payment + close)
2. Add mandatory combo modifiers

