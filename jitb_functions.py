"""
Jack in the Box Menu and Order Functions
Connects to Rust backend server for real menu data from Qu API
"""

import json
import uuid
import os
import requests
from typing import List, Dict, Any
from dotenv import load_dotenv
from latency_tracker import start_timer, end_timer
from datetime import datetime
from pathlib import Path

load_dotenv()

# Conversation log file
CONVERSATION_LOG_DIR = Path("conversation_logs")
CONVERSATION_LOG_DIR.mkdir(exist_ok=True)
CURRENT_LOG_FILE = None

def log_event(event_type: str, details: str = "", data: dict = None):
    """Log conversation events to file"""
    global CURRENT_LOG_FILE
    
    if CURRENT_LOG_FILE is None:
        return
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    log_entry = f"[{timestamp}] {event_type}"
    if details:
        log_entry += f" - {details}"
    if data:
        log_entry += f"\n    Data: {json.dumps(data, indent=4)}"
    log_entry += "\n"
    
    try:
        with open(CURRENT_LOG_FILE, 'a') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Error writing to log: {e}")

def start_conversation_log():
    """Start a new conversation log file"""
    global CURRENT_LOG_FILE
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    CURRENT_LOG_FILE = CONVERSATION_LOG_DIR / f"conversation_{timestamp}.log"
    
    with open(CURRENT_LOG_FILE, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write(f"JACK IN THE BOX VOICE AGENT - CONVERSATION LOG\n")
        f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
    
    log_event("CONVERSATION_START", "New conversation initiated")
    print(f"📝 Started conversation log: {CURRENT_LOG_FILE}")
    return str(CURRENT_LOG_FILE)

def end_conversation_log():
    """End the current conversation log"""
    global CURRENT_LOG_FILE
    
    if CURRENT_LOG_FILE:
        log_event("CONVERSATION_END", "Conversation ended")
        with open(CURRENT_LOG_FILE, 'a') as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"Ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n")
        print(f"📝 Ended conversation log: {CURRENT_LOG_FILE}")
        CURRENT_LOG_FILE = None

# Rust backend server URL
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:4000")

# Cached menu data (loaded at startup)
cached_categories = []
cached_menu = {}  # { "burgers": [...items...], "breakfast items": [...items...], ... }
cached_modifiers = {}  # { "itemPathKey": {"name": "...", "price": ...}, ... } - populated from query_modifiers results

# Load COMPLETE Qu prices (86,115 items with real prices from Qu API!)
QU_PRICES = {}
try:
    with open('qu_prices_complete.json', 'r') as f:
        price_data = json.load(f)
        QU_PRICES = price_data.get('prices', {})
    print(f"✅ Loaded {len(QU_PRICES)} real Qu prices from qu_prices_complete.json")
except Exception as e:
    print(f"⚠️  Could not load qu_prices_complete.json: {e}")
    print("   Falling back to default prices")
    QU_PRICES = {}


def get_price_by_item_path_key(item_path_key: str, item_name: str = "") -> float:
    """
    Get real Qu price for an item by itemPathKey
    
    Uses complete price data from /api/v4/menus (86,115 items)
    Fallback: $0.00 for items not found (likely included modifiers)
    """
    # Try to get real Qu price
    price = QU_PRICES.get(item_path_key)
    
    if price is not None and price > 0:
        return float(price)
    
    # If price is 0 or not found, return 0.00 (likely a modifier included in combo)
    if price is None:
        # Only log for debugging, not a warning
        print(f"ℹ️  Price not found for {item_path_key} ({item_name}), using $0.00 (likely included)")
    
    return 0.0


def estimate_price_from_name(item_name: str) -> float:
    """
    DEPRECATED: Legacy function kept for backward compatibility
    Use get_price_by_item_path_key() instead with real Qu prices
    """
    item_name_lower = item_name.lower()
    
    # Check for combo meals first (most expensive category)
    if "combo" in item_name_lower:
        # Try to find specific combo type
        if "value" in item_name_lower:
            return fallback_prices.get("combos", {}).get("value", 8.99)
        elif "premium" in item_name_lower or "ultimate" in item_name_lower:
            return fallback_prices.get("combos", {}).get("premium", 12.99)
        else:
            return fallback_prices.get("combos", {}).get("default", 10.99)
    
    # Check for breakfast items
    if "breakfast" in item_name_lower or "croissant" in item_name_lower or "burrito" in item_name_lower:
        breakfast_prices = fallback_prices.get("breakfast", {})
        # Try to match specific items
        if "breakfast jack" in item_name_lower:
            return breakfast_prices.get("breakfast_jack", 3.99)
        elif "sausage croissant" in item_name_lower:
            return breakfast_prices.get("sausage_croissant", 4.99)
        elif "burrito" in item_name_lower:
            return breakfast_prices.get("grande_sausage_burrito", 5.49)
        elif "hash brown" in item_name_lower:
            return breakfast_prices.get("hash_browns", 2.49)
        else:
            return breakfast_prices.get("default", 5.99)
    
    # Check for burgers
    if "burger" in item_name_lower or "jack" in item_name_lower:
        burger_prices = fallback_prices.get("burgers", {})
        # Try to match specific burgers
        if "jumbo jack" in item_name_lower:
            return burger_prices.get("jumbo_jack", 5.99)
        elif "double jack" in item_name_lower:
            return burger_prices.get("double_jack", 7.99)
        elif "sourdough" in item_name_lower:
            return burger_prices.get("sourdough_jack", 8.49)
        elif "buttery" in item_name_lower:
            return burger_prices.get("buttery_jack", 8.99)
        elif "bacon ultimate" in item_name_lower:
            return burger_prices.get("bacon_ultimate_cheeseburger", 9.49)
        else:
            return burger_prices.get("default", 7.99)
    
    # Check for chicken
    if "chicken" in item_name_lower and "sandwich" not in item_name_lower:
        chicken_prices = fallback_prices.get("chicken", {})
        if "strips" in item_name_lower:
            if "6" in item_name_lower:
                return chicken_prices.get("chicken_strips_6pc", 9.49)
            else:
                return chicken_prices.get("chicken_strips_4pc", 6.99)
        elif "nuggets" in item_name_lower:
            if "10" in item_name_lower:
                return chicken_prices.get("chicken_nuggets_10pc", 7.99)
            else:
                return chicken_prices.get("chicken_nuggets_5pc", 4.99)
        elif "popcorn" in item_name_lower:
            return chicken_prices.get("popcorn_chicken", 5.99)
        else:
            return chicken_prices.get("default", 6.99)
    
    # Check for sandwiches (including chicken sandwiches)
    if "sandwich" in item_name_lower:
        sandwich_prices = fallback_prices.get("sandwiches", {})
        if "spicy" in item_name_lower:
            return sandwich_prices.get("spicy_chicken", 8.49)
        elif "grilled" in item_name_lower:
            return sandwich_prices.get("grilled_chicken", 8.99)
        elif "club" in item_name_lower:
            return sandwich_prices.get("chicken_club", 9.49)
        else:
            return sandwich_prices.get("default", 8.49)
    
    # Check for tacos
    if "taco" in item_name_lower:
        taco_prices = fallback_prices.get("tacos", {})
        if "monster" in item_name_lower:
            return taco_prices.get("monster_taco", 1.99)
        elif "tiny" in item_name_lower:
            return taco_prices.get("tiny_tacos_15pc", 4.99)
        else:
            return taco_prices.get("default", 1.49)
    
    # Check for salads
    if "salad" in item_name_lower:
        salad_prices = fallback_prices.get("salads", {})
        if "side" in item_name_lower:
            return salad_prices.get("side_salad", 3.99)
        else:
            return salad_prices.get("default", 8.99)
    
    # Check for sides
    if any(word in item_name_lower for word in ["fries", "curly", "onion ring", "egg roll", "mozzarella", "jalapeno"]):
        sides_prices = fallback_prices.get("sides", {})
        if "curly" in item_name_lower:
            if "large" in item_name_lower:
                return sides_prices.get("curly_fries_large", 3.49)
            elif "medium" in item_name_lower:
                return sides_prices.get("curly_fries_medium", 2.99)
            else:
                return sides_prices.get("curly_fries_small", 2.49)
        elif "onion" in item_name_lower:
            return sides_prices.get("onion_rings", 3.49)
        elif "egg roll" in item_name_lower:
            return sides_prices.get("egg_rolls_3pc", 3.99)
        elif "mozzarella" in item_name_lower:
            return sides_prices.get("mozzarella_sticks", 4.99)
        elif "jalapeno" in item_name_lower:
            return sides_prices.get("stuffed_jalapenos_3pc", 3.99)
        else:
            return sides_prices.get("default", 2.99)
    
    # Check for drinks
    if any(word in item_name_lower for word in ["drink", "soda", "coke", "pepsi", "sprite", "shake", "coffee", "lemonade", "tea"]):
        drink_prices = fallback_prices.get("drinks", {})
        if "shake" in item_name_lower:
            if "large" in item_name_lower:
                return drink_prices.get("shake_large", 4.99)
            elif "medium" in item_name_lower:
                return drink_prices.get("shake_medium", 4.29)
            else:
                return drink_prices.get("shake_small", 3.49)
        elif "coffee" in item_name_lower:
            if "iced" in item_name_lower:
                return drink_prices.get("iced_coffee", 2.99)
            else:
                return drink_prices.get("hot_coffee", 2.29)
        elif "lemonade" in item_name_lower:
            return drink_prices.get("lemonade", 2.49)
        elif "tea" in item_name_lower:
            return drink_prices.get("iced_tea", 2.29)
        else:
            # Generic soda
            if "large" in item_name_lower:
                return drink_prices.get("soda_large", 2.69)
            elif "medium" in item_name_lower:
                return drink_prices.get("soda_medium", 2.29)
            else:
                return drink_prices.get("soda_small", 1.99)
    
    # Check for desserts
    if any(word in item_name_lower for word in ["dessert", "churro", "cheesecake", "turnover", "cake", "pie"]):
        dessert_prices = fallback_prices.get("desserts", {})
        if "churro" in item_name_lower:
            return dessert_prices.get("mini_churros", 2.49)
        elif "cheesecake" in item_name_lower:
            return dessert_prices.get("cheesecake", 3.49)
        elif "turnover" in item_name_lower:
            return dessert_prices.get("apple_turnover", 1.99)
        elif "chocolate" in item_name_lower:
            return dessert_prices.get("chocolate_cake", 3.99)
        elif "pie" in item_name_lower:
            return dessert_prices.get("pie_slice", 2.49)
        else:
            return dessert_prices.get("default", 2.99)
    
    # Default fallback
    return 8.99


def load_menu_categories():
    """Load the full menu at startup and cache both categories and items for faster responses"""
    global cached_categories, cached_menu
    
    try:
        print("📋 Loading FULL menu from cached Qu API data...")
        
        # Get FULL cached menu from Rust backend (includes ALL items in tree structure)
        response = requests.get(
            f"{BACKEND_URL}/menu",
            timeout=15
        )
        response.raise_for_status()
        menu_data = response.json()
        
        # Extract categories from the hierarchical menu structure
        categories = menu_data.get("value", {}).get("categories", [])
        if not categories:
            print("⚠️  No menu categories found, using default categories")
            cached_categories = ["Breakfast", "Lunch/Dinner", "Snacks, Sides & Extras", "Drinks", "Kid's Meals", "Late Night & LTOs", "Extras"]
            return
        
        print(f"   Found {len(categories)} top-level categories from Qu")
        
        # Recursively extract all items from the tree structure
        def extract_items(node, depth=0):
            """Recursively extract items from the menu tree"""
            items_list = []
            
            title = node.get("title", "")
            item_path_key = node.get("itemPathKey", "")
            description = node.get("displayAttribute", {}).get("description", "")
            
            # Skip empty titles
            if not title:
                return items_list
            
            # Skip modifiers (they start with "Mod -" or "Modifier -")
            if title.startswith("Mod -") or title.startswith("Modifier -"):
                return items_list
            
            # Add current item if it has an itemPathKey (leaf node with actual product)
            if item_path_key:
                # Get price
                price = get_price_by_item_path_key(item_path_key, title)
                
                # Skip items with $0.00 price (system/internal items)
                if price > 0:
                    items_list.append({
                        "title": title,
                        "itemPathKey": item_path_key,
                        "price": price,
                        "description": description
                    })
            
            # Recursively process children
            children = node.get("children", [])
            for child in children:
                items_list.extend(extract_items(child, depth + 1))
            
            return items_list
        
        # Organize items by Qu's EXACT top-level categories
        temp_menu = {}
        categories_set = set()
        
        for category_node in categories:
            category_title = category_node.get("title", "")
            if not category_title:
                continue
            
            # Extract all items from this category
            category_items = extract_items(category_node)
            
            if category_items:  # Only add if it has items with prices
                categories_set.add(category_title)
                temp_menu[category_title] = []
                
                for item in category_items:
                    temp_menu[category_title].append({
                        "name": item.get("title", ""),
                    "itemPathKey": item.get("itemPathKey", ""),
                    "price": item.get("price", 0.0),
                    "description": item.get("description", "")
                })
        
        # Use Qu's category order (don't sort alphabetically)
        cached_categories = list(categories_set)
        cached_menu = temp_menu
        
        # Create virtual "Desserts" category by extracting all dessert items
        dessert_items = []
        for category_name, category_items in temp_menu.items():
            if not isinstance(category_items, list):
                continue
            for item in category_items:
                if not isinstance(item, dict):
                    continue
                item_name = item.get("name", "")
                if isinstance(item_name, str) and item_name.startswith("Dessert -"):
                    # Create a copy to avoid modifying the original
                    dessert_items.append(item.copy())
        
        # Add Desserts category if we found any dessert items
        if dessert_items:
            cached_menu["Desserts"] = dessert_items
            cached_categories.append("Desserts")
            print(f"   ✨ Created virtual 'Desserts' category with {len(dessert_items)} items")
        
        # Print summary
        total_items = sum(len(items) for items in cached_menu.values())
        print(f"✅ Loaded {len(cached_categories)} categories with {total_items} items:")
        for cat in cached_categories:
            item_count = len(cached_menu.get(cat, []))
            print(f"   • {cat}: {item_count} items")
        
    except Exception as e:
        print(f"⚠️  Could not load menu: {e}")
        import traceback
        traceback.print_exc()
        print("   Using default categories")
        cached_categories = ["Breakfast", "Lunch/Dinner", "Snacks, Sides & Extras", "Drinks", "Kid's Meals", "Late Night & LTOs", "Extras"]
        cached_menu = {}


def get_menu_categories() -> str:
    """Get cached menu categories (fast!)"""
    if not cached_categories:
        return json.dumps({
            "categories": ["Breakfast", "Lunch/Dinner", "Snacks, Sides & Extras", "Drinks", "Kid's Meals", "Late Night & LTOs", "Extras"],
            "cached": False
        })
    
    return json.dumps({
        "categories": cached_categories,
        "cached": True
    })


def get_category_items(category: str) -> str:
    """Get cached items for a specific category (instant!)"""
    # Try exact match first (case-insensitive)
    category_match = None
    category_lower = category.lower().strip()
    
    for cat_name in cached_menu.keys():
        if cat_name.lower() == category_lower:
            category_match = cat_name
            break
    
    # If no exact match, try fuzzy matching
    if not category_match:
        for cat_name in cached_menu.keys():
            if category_lower in cat_name.lower() or cat_name.lower() in category_lower:
                category_match = cat_name
                break
    
    # Get items from cache
    items = cached_menu.get(category_match, []) if category_match else []
    
    if not items:
        return json.dumps({
            "success": False,
            "category": category,
            "items": [],
            "message": f"No items found for category '{category}'",
            "cached": True
        })
    
    return json.dumps({
        "success": True,
        "category": category_lower,
        "items": items,
        "count": len(items),
        "cached": True
    })


# Mock menu database
MENU_ITEMS = {
    # Burgers
    "sourdough-jack-combo": {
        "itemPathKey": "sourdough-jack-combo",
        "name": "Sourdough Jack Combo",
        "category": "burgers",
        "price": 8.99,
        "description": "Sourdough burger with bacon"
    },
    "double-jack-combo": {
        "itemPathKey": "double-jack-combo",
        "name": "Double Jack Combo",
        "category": "burgers",
        "price": 9.49,
        "description": "Double patty burger"
    },
    "jumbo-jack-combo": {
        "itemPathKey": "jumbo-jack-combo",
        "name": "Jumbo Jack Combo",
        "category": "burgers",
        "price": 7.99,
        "description": "Classic Jumbo Jack"
    },
    "ultimate-cheeseburger-combo": {
        "itemPathKey": "ultimate-cheeseburger-combo",
        "name": "Ultimate Cheeseburger Combo",
        "category": "burgers",
        "price": 9.99,
        "description": "Two beef patties with cheese"
    },
    
    # Chicken
    "homestyle-chicken-combo": {
        "itemPathKey": "homestyle-chicken-combo",
        "name": "Homestyle Chicken Combo",
        "category": "chicken",
        "price": 8.49,
        "description": "Crispy chicken sandwich"
    },
    "spicy-chicken-combo": {
        "itemPathKey": "spicy-chicken-combo",
        "name": "Spicy Chicken Combo",
        "category": "chicken",
        "price": 8.49,
        "description": "Spicy crispy chicken"
    },
    "chicken-nuggets-8pc-combo": {
        "itemPathKey": "chicken-nuggets-8pc-combo",
        "name": "8 Piece Chicken Nuggets Combo",
        "category": "chicken",
        "price": 7.99,
        "description": "8 piece nuggets"
    },
    
    # Breakfast
    "supreme-croissant-combo": {
        "itemPathKey": "supreme-croissant-combo",
        "name": "Supreme Croissant Combo",
        "category": "breakfast",
        "price": 6.99,
        "description": "Egg, sausage, bacon on croissant"
    },
    "loaded-breakfast-sandwich-combo": {
        "itemPathKey": "loaded-breakfast-sandwich-combo",
        "name": "Loaded Breakfast Sandwich Combo",
        "category": "breakfast",
        "price": 5.99,
        "description": "Loaded breakfast sandwich"
    },
    
    # Sides (singles)
    "curly-fries-small": {
        "itemPathKey": "curly-fries-small",
        "name": "Curly Fries (Small)",
        "category": "sides",
        "price": 2.49
    },
    "curly-fries-medium": {
        "itemPathKey": "curly-fries-medium",
        "name": "Curly Fries (Medium)",
        "category": "sides",
        "price": 2.99
    },
    "curly-fries-large": {
        "itemPathKey": "curly-fries-large",
        "name": "Curly Fries (Large)",
        "category": "sides",
        "price": 3.49
    },
    "regular-fries-small": {
        "itemPathKey": "regular-fries-small",
        "name": "Regular Fries (Small)",
        "category": "sides",
        "price": 2.29
    },
    "onion-rings": {
        "itemPathKey": "onion-rings",
        "name": "Onion Rings",
        "category": "sides",
        "price": 3.29
    },
    
    # Drinks (singles)
    "coke": {
        "itemPathKey": "coke",
        "name": "Coca-Cola",
        "category": "drinks",
        "price": 2.29
    },
    "sprite": {
        "itemPathKey": "sprite",
        "name": "Sprite",
        "category": "drinks",
        "price": 2.29
    },
    "fanta-orange": {
        "itemPathKey": "fanta-orange",
        "name": "Fanta Orange",
        "category": "drinks",
        "price": 2.29
    },
    "iced-coffee": {
        "itemPathKey": "iced-coffee",
        "name": "Iced Coffee",
        "category": "drinks",
        "price": 2.99
    },
    "orange-juice": {
        "itemPathKey": "orange-juice",
        "name": "Orange Juice",
        "category": "drinks",
        "price": 2.49
    },
    
    # Desserts
    "chocolate-shake": {
        "itemPathKey": "chocolate-shake",
        "name": "Chocolate Shake",
        "category": "desserts",
        "price": 3.99
    },
    "oreo-shake": {
        "itemPathKey": "oreo-shake",
        "name": "Oreo Shake",
        "category": "desserts",
        "price": 4.49
    },
}

# Modifiers (for combo customization)
MODIFIERS = {
    "curly-fries-side": {
        "itemPathKey": "curly-fries-side",
        "name": "Curly Fries",
        "modifierType": "side",
        "price": 0.0
    },
    "regular-fries-side": {
        "itemPathKey": "regular-fries-side",
        "name": "Regular Fries",
        "modifierType": "side",
        "price": 0.0
    },
    "onion-rings-side": {
        "itemPathKey": "onion-rings-side",
        "name": "Onion Rings",
        "modifierType": "side",
        "price": 0.50
    },
    "coke-drink": {
        "itemPathKey": "coke-drink",
        "name": "Coca-Cola",
        "modifierType": "drink",
        "price": 0.0
    },
    "sprite-drink": {
        "itemPathKey": "sprite-drink",
        "name": "Sprite",
        "modifierType": "drink",
        "price": 0.0
    },
    "fanta-drink": {
        "itemPathKey": "fanta-drink",
        "name": "Fanta Orange",
        "modifierType": "drink",
        "price": 0.0
    },
    "no-pickles": {
        "itemPathKey": "no-pickles",
        "name": "No Pickles",
        "modifierType": "customization",
        "price": 0.0
    },
    "extra-cheese": {
        "itemPathKey": "extra-cheese",
        "name": "Extra Cheese",
        "modifierType": "customization",
        "price": 0.75
    },
}

# Current order (in-memory)
current_order: List[Dict[str, Any]] = []
qu_order_id: str = None  # Store Qu order ID when submitted


def get_qu_jwt_token() -> str:
    """Get JWT token from Qu API for authentication"""
    try:
        qu_secret = os.getenv("QU_SECRET")
        if not qu_secret:
            raise Exception("QU_SECRET not found in environment")
        
        response = requests.post(
            "https://gateway-api.qubeyond.com/api/v4/authentication/oauth2/access-token",
            data={
                "grant_type": "client_credentials",
                "client_id": "deepgramjitb405",
                "client_secret": qu_secret,
                "scope": "menu:*"
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        return data.get("access_token")
    except Exception as e:
        print(f"Error getting Qu JWT token: {e}")
        return None


def submit_order_to_qu() -> str:
    """Submit the current order to Qu API (or simulate submission)"""
    log_event("FUNCTION_CALL", f"submit_order_to_qu", {"items_count": len(current_order)})
    if not current_order:
        return json.dumps({
            "success": False,
            "message": "Cannot submit empty order"
        })
    
    # Calculate total (item prices already include modifier prices from add_modifier)
    print("\n💰 Calculating order total:")
    total = 0
    for idx, item in enumerate(current_order, 1):
        item_price = item.get("price", 8.99)
        item_name = item.get('name') or item.get('itemName', 'Item')
        print(f"   {idx}. {item_name}: ${item_price:.2f}")
        
        # Modifiers should already be included in item price
        if item.get('modifiers'):
            for mod in item['modifiers']:
                mod_price = mod.get('price', 0)
                print(f"      + {mod.get('name', 'Modifier')}: ${mod_price:.2f} (already included in item price)")
        
        total += item_price
    
    print(f"   TOTAL: ${total:.2f}\n")
    
    # Generate order ID
    global qu_order_id
    qu_order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    
    # Log the order (for demo purposes)
    print(f"\n📋 Order Summary:")
    print(f"   Order ID: {qu_order_id}")
    print(f"   Items: {len(current_order)}")
    for idx, item in enumerate(current_order, 1):
        # Get item name (check both 'name' and 'itemName' fields)
        item_name = item.get('name') or item.get('itemName', 'Item')
        print(f"   {idx}. {item_name} (${item.get('price', 8.99):.2f})")
        if item.get('modifiers'):
            for mod in item['modifiers']:
                print(f"      + {mod.get('name', 'Modifier')}")
    print(f"   Total: ${total:.2f}\n")
    
    # Try to submit to Qu API (if available)
    try:
        token = get_qu_jwt_token()
        if token:
            qu_order = {
                "orderType": "DINE_IN",
                "items": []
            }
            
            for item in current_order:
                qu_item = {
                    "itemPathKey": item.get("itemPathKey"),
                    "quantity": item.get("quantity", 1),
                    "modifiers": [m.get("itemPathKey") for m in item.get("modifiers", [])]
                }
                qu_order["items"].append(qu_item)
            
            # Attempt submission
            response = requests.post(
                "https://gateway-api.qubeyond.com/api/v4/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json=qu_order,
                timeout=5
            )
            
            if response.status_code == 200 or response.status_code == 201:
                order_data = response.json()
                qu_order_id = order_data.get("orderId") or order_data.get("id") or qu_order_id
                print(f"✅ Order submitted to Qu API: {qu_order_id}")
                
                return json.dumps({
                    "success": True,
                    "order_id": qu_order_id,
                    "total": round(total, 2),
                    "message": "Order submitted successfully to Qu",
                    "submitted_to_qu": True
                })
    except Exception as e:
        # Qu submission failed - log but continue with simulated success
        print(f"⚠️  Qu API submission failed: {str(e)}")
        print(f"📝 Order saved locally with ID: {qu_order_id}")
    
    # Return success with simulated submission
    return json.dumps({
        "success": True,
        "order_id": qu_order_id,
        "total": round(total, 2),
        "item_count": len(current_order),
        "message": "Order confirmed and saved",
        "submitted_to_qu": False,
        "note": "Order saved locally (Qu API submission requires additional permissions)"
    })




def order() -> str:
    """Get all details about the current order"""
    if not current_order:
        return json.dumps({
            "order_id": None,
            "items": [],
            "total": 0.0,
            "message": "Order is empty"
        })
    
    total = sum(item.get("price", 0) for item in current_order)
    
    result = {
        "order_id": qu_order_id or "ORD-12345",
        "items": current_order,
        "item_count": len(current_order),
        "total": round(total, 2),
        "submitted_to_qu": qu_order_id is not None
    }
    
    return json.dumps(result, indent=2)


def query_items(query: str, limit: int = 5) -> str:
    """Query available menu items from Rust backend server"""
    log_event("FUNCTION_CALL", f"query_items", {"query": query, "limit": limit})
    start_timer("qu_query_items")
    try:
        response = requests.post(
            f"{BACKEND_URL}/query/items",
            json={"query": query, "limit": limit},
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        end_timer("qu_query_items", {"query": query, "result_count": len(data.get("items", []))})
        
        # Format the response
        items = data.get("items", [])
        if not items:
            return json.dumps({
                "results": [],
                "message": f"No items found matching '{query}'"
            })
        
        # Transform to expected format
        results = []
        for item in items:
            results.append({
                "itemPathKey": item.get("item_path_key", item.get("itemPathKey", "")),
                "name": item.get("title", item.get("name", "")),  # Rust backend uses "title"
                "category": item.get("category", ""),
                "price": item.get("price", 0.0),
                "description": item.get("description", item.get("displayAttribute", {}).get("description", ""))
            })
        
        return json.dumps({
            "results": results,
            "count": len(results)
        }, indent=2)
        
    except requests.exceptions.RequestException as e:
        # Fallback to mock data if server is unavailable
        print(f"Warning: Could not reach backend server: {e}")
        print("Falling back to mock menu data...")
        
        query_lower = query.lower()
        matches = []
        for item in MENU_ITEMS.values():
            name_lower = item["name"].lower()
            if any(word in name_lower for word in query_lower.split()):
                matches.append({
                    "itemPathKey": item["itemPathKey"],
                    "name": item["name"],
                    "category": item["category"],
                    "price": item["price"],
                    "description": item.get("description", "")
                })
        
        matches = matches[:limit]
        return json.dumps({
            "results": matches,
            "count": len(matches),
            "warning": "Using mock data - backend server unavailable"
        }, indent=2)


def query_modifiers(query: str, parent: str, limit: int = 5) -> str:
    """Query available modifiers for an item from Rust backend server"""
    log_event("FUNCTION_CALL", f"query_modifiers", {"query": query, "parent": parent, "limit": limit})
    global cached_modifiers
    start_timer("qu_query_modifiers")
    try:
        response = requests.post(
            f"{BACKEND_URL}/query/modifiers",
            json={"query": query, "parent": parent, "limit": limit},
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        end_timer("qu_query_modifiers", {"query": query, "parent": parent[:20], "result_count": len(data.get("results", []))})
        
        # Format the response
        items = data.get("items", [])
        results = []
        for item in items:
            item_path_key = item.get("item_path_key", item.get("itemPathKey", ""))
            item_name = item.get("title", item.get("name", ""))
            item_price = item.get("price", 0.0)
            
            # Cache this modifier for later use in add_modifier
            cached_modifiers[item_path_key] = {
                "name": item_name,
                "price": item_price
            }
            
            results.append({
                "itemPathKey": item_path_key,
                "name": item_name,
                "modifierType": item.get("modifier_type", item.get("modifierType", "")),
                "price": item_price
            })
        
        return json.dumps({
            "parent": parent,
            "results": results,
            "count": len(results)
        }, indent=2)
        
    except requests.exceptions.RequestException as e:
        # Fallback to mock data if server is unavailable
        print(f"Warning: Could not reach backend server: {e}")
        print("Falling back to mock modifier data...")
        
        query_lower = query.lower()
        matches = []
        for mod in MODIFIERS.values():
            name_lower = mod["name"].lower()
            if any(word in name_lower for word in query_lower.split()):
                matches.append({
                    "itemPathKey": mod["itemPathKey"],
                    "name": mod["name"],
                    "modifierType": mod["modifierType"],
                    "price": mod["price"]
                })
        
        matches = matches[:limit]
        return json.dumps({
            "parent": parent,
            "results": matches,
            "count": len(matches),
            "warning": "Using mock data - backend server unavailable"
        }, indent=2)


def add_item(itemPathKey: str) -> str:
    """Add an item to the order"""
    log_event("FUNCTION_CALL", f"add_item", {"itemPathKey": itemPathKey})
    # Try to find in mock menu first
    if itemPathKey in MENU_ITEMS:
        item = MENU_ITEMS[itemPathKey].copy()
        item_id = str(uuid.uuid4())
        item["itemId"] = item_id
        item["modifiers"] = []
        
        current_order.append(item)
        
        return json.dumps({
            "success": True,
            "itemId": item_id,
            "itemPathKey": itemPathKey,
            "itemName": item["name"],
            "price": item["price"],
            "message": f"Added {item['name']} to order"
        }, indent=2)
    
    # Try to find in cached menu from Qu API
    item_name = None
    
    for category, items in cached_menu.items():
        for cached_item in items:
            if cached_item.get("itemPathKey") == itemPathKey:
                item_name = cached_item.get("name", f"Item {itemPathKey}")
                break
        if item_name:
            break
    
    # If not found in cache, use generic name
    if not item_name:
        item_name = f"Item {itemPathKey}"
    
    # Get REAL Qu price for this item
    item_price = get_price_by_item_path_key(itemPathKey, item_name)
    
    # Create item entry
    item_id = str(uuid.uuid4())
    new_item = {
        "itemPathKey": itemPathKey,
        "itemId": item_id,
        "name": item_name,
        "price": item_price,
        "modifiers": []
    }
    
    current_order.append(new_item)
    
    return json.dumps({
        "success": True,
        "itemId": item_id,
        "itemPathKey": itemPathKey,
        "itemName": item_name,
        "price": item_price,
        "message": f"Added {item_name} to order"
    }, indent=2)


def delete_item(itemId: str) -> str:
    """Remove an item from the order"""
    log_event("FUNCTION_CALL", f"delete_item", {"itemId": itemId})
    global current_order
    
    # Find and remove item
    original_count = len(current_order)
    current_order = [item for item in current_order if item.get("itemId") != itemId]
    
    if len(current_order) < original_count:
        return json.dumps({
            "success": True,
            "itemId": itemId,
            "message": f"Item removed from order"
        })
    else:
        return json.dumps({
            "success": False,
            "itemId": itemId,
            "error": f"Item with ID '{itemId}' not found in order"
        })


def add_modifier(itemPathKey: str, itemId: str) -> str:
    """Add a modifier to an item in the order"""
    log_event("FUNCTION_CALL", f"add_modifier", {"itemPathKey": itemPathKey, "itemId": itemId})
    # Find the item in order
    target_item = None
    for item in current_order:
        if item.get("itemId") == itemId:
            target_item = item
            break
    
    if not target_item:
        return json.dumps({
            "success": False,
            "error": f"Item with ID '{itemId}' not found in order"
        })
    
    # Try to find modifier in multiple sources:
    # 1. Mock data (MODIFIERS)
    # 2. Cached modifiers from recent query_modifiers calls
    # 3. Direct Qu price lookup
    
    if itemPathKey in MODIFIERS:
        modifier = MODIFIERS[itemPathKey].copy()
    elif itemPathKey in cached_modifiers:
        # Use cached modifier from query_modifiers
        cached_mod = cached_modifiers[itemPathKey]
        modifier_name = cached_mod["name"]
        
        # Check if this is a combo modifier (itemPathKey is a child of the parent item)
        parent_item_path_key = target_item.get("itemPathKey", "")
        is_combo_modifier = itemPathKey.startswith(parent_item_path_key + "-")
        
        if is_combo_modifier:
            # Combo modifiers are included at no extra charge
            modifier_price = 0.0
            print(f"   ℹ️  '{modifier_name}' is included in combo (no extra charge)")
        else:
            # Standalone modifiers have their own price
            modifier_price = get_price_by_item_path_key(itemPathKey, modifier_name)
            print(f"   💰 '{modifier_name}' is an extra charge: ${modifier_price:.2f}")
        
        modifier = {
            "itemPathKey": itemPathKey,
            "name": modifier_name,
            "price": modifier_price
        }
    else:
        # Direct Qu price lookup - try to find modifier name
        parent_item_path_key = target_item.get("itemPathKey", "")
        is_combo_modifier = itemPathKey.startswith(parent_item_path_key + "-")
        
        # Try to get a better name by looking it up in the backend
        modifier_name = "Modifier"
        try:
            # Query the Rust backend for this specific modifier
            response = requests.post(
                f"{BACKEND_URL}/query/modifiers",
                json={"parent": parent_item_path_key, "query": "", "limit": 100},
                timeout=3
            )
            if response.status_code == 200:
                data = response.json()
                for mod in data.get("results", []):
                    if mod.get("itemPathKey") == itemPathKey:
                        modifier_name = mod.get("name", "Modifier")
                        break
        except:
            pass  # Fallback to generic name
        
        if is_combo_modifier:
            modifier_price = 0.0
            print(f"   ℹ️  '{modifier_name}' is included in combo (no extra charge)")
        else:
            modifier_price = get_price_by_item_path_key(itemPathKey, modifier_name)
            print(f"   💰 '{modifier_name}' is an extra charge: ${modifier_price:.2f}")
        
        modifier = {
            "itemPathKey": itemPathKey,
            "name": modifier_name,
            "price": modifier_price
        }
    
    # Check if we're replacing an existing modifier of the same type (e.g., fries with fries)
    # If the modifier is a side/drink for a combo, replace any existing side/drink of same category
    parent_item_path_key = target_item.get("itemPathKey", "")
    if itemPathKey.startswith(parent_item_path_key + "-"):
        # This is a combo modifier - check if we're replacing one
        modifier_category = None
        if "fries" in modifier["name"].lower() or "side" in modifier["name"].lower():
            modifier_category = "side"
        elif "drink" in modifier["name"].lower() or "beverage" in modifier["name"].lower():
            modifier_category = "drink"
        
        if modifier_category:
            # Remove any existing modifier of the same category
            existing_modifiers = target_item["modifiers"]
            for i, existing_mod in enumerate(existing_modifiers):
                existing_name = existing_mod.get("name", "").lower()
                if modifier_category == "side" and ("fries" in existing_name or "side" in existing_name):
                    # Replace the side
                    target_item["price"] -= existing_mod["price"]
                    target_item["modifiers"].pop(i)
                    print(f"   🔄 Replacing {existing_mod['name']} with {modifier['name']}")
                    break
                elif modifier_category == "drink" and ("drink" in existing_name or "beverage" in existing_name or "coke" in existing_name or "sprite" in existing_name or "juice" in existing_name):
                    # Replace the drink
                    target_item["price"] -= existing_mod["price"]
                    target_item["modifiers"].pop(i)
                    print(f"   🔄 Replacing {existing_mod['name']} with {modifier['name']}")
                    break
    
    target_item["modifiers"].append(modifier)
    target_item["price"] += modifier["price"]
    
    return json.dumps({
        "success": True,
        "itemId": itemId,
        "itemPathKey": itemPathKey,
        "modifier_name": modifier["name"],
        "modifier_price": modifier["price"],
        "message": f"Added {modifier['name']} to {target_item.get('itemName', target_item.get('name', 'item'))}"
    }, indent=2)


# Function mapping for easy lookup
FUNCTION_MAP = {
    "order": order,
    "query_items": query_items,
    "query_modifiers": query_modifiers,
    "add_item": add_item,
    "delete_item": delete_item,
    "add_modifier": add_modifier,
    "submit_order_to_qu": submit_order_to_qu,
    "get_menu_categories": get_menu_categories,
    "get_category_items": get_category_items,
}


if __name__ == "__main__":
    # Test the functions
    print("=== Testing query_items ===")
    print(query_items("burger", limit=3))
    
    print("\n=== Testing add_item ===")
    result = json.loads(add_item("sourdough-jack-combo"))
    print(json.dumps(result, indent=2))
    item_id = result.get("itemId")
    
    print("\n=== Testing query_modifiers ===")
    print(query_modifiers("curly fries", parent="sourdough-jack-combo"))
    
    print("\n=== Testing add_modifier ===")
    print(add_modifier("curly-fries-side", item_id))
    
    print("\n=== Testing order ===")
    print(order())
    
    print("\n=== Testing delete_item ===")
    print(delete_item(item_id))
    
    print("\n=== Final order ===")
    print(order())

