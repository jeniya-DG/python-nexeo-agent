#!/usr/bin/env python3
"""
Get Full Menu with Prices from /api/v4/menus
This endpoint includes priceAttribute which should give us direct price data!
"""

import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

QU_BASE_URL = "https://gateway-api.qubeyond.com/api/v4"
LOCATION_ID = os.getenv("LOCATION_ID", "4776")
QU_SECRET = os.getenv("QU_SECRET")
CLIENT_ID = "deepgramjitb405"
X_INTEGRATION = os.getenv("X_INTEGRATION", "682c4b47f7e426d4b8208962")

def get_qu_jwt_token():
    """Get JWT token for Qu API authentication"""
    try:
        response = requests.post(
            f"{QU_BASE_URL}/authentication/oauth2/access-token",
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": QU_SECRET,
                "scope": "menu:*"
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        return data.get("access_token")
    except Exception as e:
        print(f"❌ Error getting Qu JWT token: {e}")
        return None

def get_location_context(token):
    """
    Get OrderChannelId and OrderTypeId dynamically from location details
    Returns: (order_channel_id, order_type_id)
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Integration": X_INTEGRATION,
    }
    
    params = {
        "IncludeContextOptions": "true",
        "FulfillmentMethod": "1"  # Pickup/Drive-thru
    }
    
    url = f"{QU_BASE_URL}/locations/{LOCATION_ID}"
    
    print(f"\n📍 Getting location context from Qu API...")
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            value = data.get("value", {})
            context = value.get("contextOptions", {})
            
            order_channel_id = context.get("defaultOrderChannelId")
            order_types = context.get("orderTypes", [])
            order_type_id = order_types[0].get("id") if order_types else None
            
            if order_channel_id and order_type_id:
                print(f"   ✅ OrderChannelId: {order_channel_id}")
                print(f"   ✅ OrderTypeId: {order_type_id}")
                return (str(order_channel_id), str(order_type_id))
            else:
                print(f"   ⚠️  Could not extract context from location details")
                return (None, None)
        else:
            print(f"   ❌ Failed to get location details: {response.status_code}")
            return (None, None)
            
    except Exception as e:
        print(f"   ❌ Error getting location context: {e}")
        return (None, None)

def get_full_menu_with_prices(token, order_channel_id, order_type_id):
    """
    Get full menu with prices from /api/v4/menus
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Integration": X_INTEGRATION,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Use dynamically fetched values from location context
    params = {
        "LocationId": LOCATION_ID,
        "OrderChannelId": order_channel_id,
        "OrderTypeId": order_type_id,
    }
    
    url = f"{QU_BASE_URL}/menus"
    
    print(f"\n📍 GET {url}")
    print(f"   Parameters: {params}")
    print(f"   ⚠️  Note: This endpoint can return up to 300MB of data!")
    
    try:
        print(f"\n⏳ Downloading full menu (this may take a moment)...")
        response = requests.get(url, headers=headers, params=params, timeout=60)
        
        print(f"📥 Response: {response.status_code}")
        
        if response.status_code == 200:
            print(f"   ✅ Success!")
            print(f"   📦 Response size: {len(response.content) / 1024 / 1024:.2f} MB")
            
            data = response.json()
            
            # Save to file
            output_file = "full_menu_with_prices.json"
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"   💾 Saved to: {output_file}")
            
            return data
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"   {response.text[:500]}")
            return None
            
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return None

def extract_prices_from_menu(menu_data):
    """
    Extract prices from full menu data
    Recursively traverse the tree and extract priceAttribute
    """
    price_map = {}
    count = 0
    
    def traverse(item, depth=0):
        nonlocal count
        item_path_key = item.get("itemPathKey")
        title = item.get("title", "")
        price_attr = item.get("priceAttribute")
        
        if item_path_key and price_attr:
            # Extract price from priceAttribute.prices array
            prices_list = price_attr.get("prices", [])
            if prices_list and len(prices_list) > 0:
                price_obj = prices_list[0]  # Get first price
                price = price_obj.get("price", 0.0)
                price_value_id = price_obj.get("priceValueId")
                
                if price > 0:
                    # Store just the price number (jitb_functions.py expects floats, not objects)
                    price_map[item_path_key] = price
                    count += 1
                    
                    if count <= 20:  # Only print first 20
                        indent = "  " * min(depth, 3)
                        print(f"{indent}✅ {title[:50]:<50} ${price:.2f}")
                    elif count == 21:
                        print(f"   ... ({count-20} more items, suppressing output)")
        
        # Traverse children
        for child in item.get("children", []):
            traverse(child, depth + 1)
    
    # Start traversal from root
    if "children" in menu_data:
        print("\n📊 Extracting prices from menu tree...")
        for child in menu_data["children"]:
            traverse(child)
    
    return price_map

def main():
    print("=" * 80)
    print("🔍 Get Full Menu with Prices (/api/v4/menus)")
    print("=" * 80)
    
    # Get authentication token
    print("\n🔐 Authenticating...")
    token = get_qu_jwt_token()
    
    if not token:
        print("❌ Failed to authenticate")
        return
    
    print("✅ Authenticated")
    
    # Get location context (OrderChannelId and OrderTypeId)
    order_channel_id, order_type_id = get_location_context(token)
    
    if not order_channel_id or not order_type_id:
        print("❌ Failed to get location context")
        return
    
    # Get full menu with prices
    menu_data = get_full_menu_with_prices(token, order_channel_id, order_type_id)
    
    if not menu_data:
        print("❌ Failed to get menu data")
        return
    
    # Extract prices
    price_map = extract_prices_from_menu(menu_data)
    
    print(f"\n📊 Summary:")
    print(f"   ✅ Extracted {len(price_map)} items with prices")
    
    if len(price_map) > 0:
        # Save price map (this is what jitb_functions.py loads!)
        output_file = "qu_prices_complete.json"
        with open(output_file, 'w') as f:
            json.dump({
                "extracted_at": datetime.now().isoformat(),
                "source": "/api/v4/menus (Full Menu with Dynamic Context)",
                "location_id": LOCATION_ID,
                "price_count": len(price_map),
                "prices": price_map
            }, f, indent=2)
        
        print(f"   💾 Saved price map to: {output_file}")
        
        # Display sample
        print(f"\n💰 Sample Prices (first 10):")
        print(f"{'Item Path Key':<30} {'Price':<10}")
        print("-" * 42)
        for idx, (item_path_key, price) in enumerate(list(price_map.items())[:10]):
            print(f"{item_path_key:<30} ${price:<9.2f}")
    
    print("\n" + "=" * 80)
    print(f"✅ Complete!")
    print("=" * 80)

if __name__ == "__main__":
    main()

