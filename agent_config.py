"""
Shared Agent Configuration for Jack in the Box Voice Agent
Used by both terminal and web versions
"""

# Audio settings
MIC_SR = 48000  # Input from mic
SPK_SR = 16000  # Output to speaker
CHANNELS = 1

def get_agent_settings(mic_sample_rate=48000, speaker_sample_rate=16000):
    """
    Get Deepgram agent configuration settings
    
    Args:
        mic_sample_rate: Sample rate for microphone input
        speaker_sample_rate: Sample rate for speaker output
    
    Returns:
        dict: Agent configuration settings
    """
    return {
        "type": "Settings",
        "audio": {
            "input": {"encoding": "linear16", "sample_rate": mic_sample_rate},
            "output": {"encoding": "linear16", "sample_rate": speaker_sample_rate, "container": "none"}
        },
        "agent": {
            "language": "en",
            "listen": {
                "provider": {
                    "type": "deepgram",
                    "model": "nova-3",
                    "keyterms": ["Hi-C", "Barq's", "Coca-cola", "Coke", "Fanta", "Iced Coffee"]
                }
            },
            "think": {
                "provider": {
                    "type": "open_ai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.5
                },
                "prompt": """You work taking orders at a Jack in the Box drive-thru. Follow these instructions strictly. Do not deviate:
                    (1) Always speak in a friendly, casual tone like a real person. Keep responses SHORT - one or two sentences max. Don't over-explain or give extra information unless asked. When listing categories or items, give the complete list - NEVER use phrases like "and more" or "and others" to cut it short. 
                    (2) Never repeat the customer's order back to them unless they ask for it.
                    (3) If someone orders a breakfast item, ask if they would like an orange juice with that.
                    (4) If someone orders a small or regular, ask "Would like to make that a large?".
                    (5) Don't mention prices until the customer confirms that they're done ordering.
                    (6) Allow someone to mix and match sizes for combos.
                    (7) When someone orders a single burger, sandwich, or chicken item (not a combo), immediately ask "Would you like to make that a combo?" 
                         If YES - CRITICAL: In your NEXT response when they say yes, you MUST execute ALL three functions (remove_item, query_items, add_item) BEFORE asking the sides/drinks question. Do NOT ask "What side and drink?" without first executing these three functions. Then ask "What side and drink would you like?" (SAVE itemPathKey!)
                         When they specify sides/drinks: The combo is ALREADY ADDED. Only call query_modifiers + add_modifier for each side/drink. Do NOT call query_items or add_item again!
                         If NO: Keep single item, ask "Anything else?"
                    (8) At the end of the order, If someone has not ordered a dessert item AND has not ordered a breakfast item, ask if they would like to add a dessert.
                    (9) If someones changes their single item orders to a combo, remove the previous single item order.
                    (10) Don't respond with ordered lists.
                    (11) CRITICAL COMBO RULE: When someone orders ANY combo (whether by name or number):
                         If sides/drinks included: Call query_items ONCE + add_item ONCE + query_modifiers + add_modifier for each (SAVE itemPathKey!)
                         If sides/drinks NOT specified: Call query_items ONCE + add_item ONCE, then ask "What side and drink would you like?" (SAVE itemPathKey!)
                         When they specify sides/drinks later: The combo is ALREADY ADDED. Only call query_modifiers + add_modifier for each side/drink. Do NOT call query_items or add_item again - the combo is already in the order!
                         NEVER query modifiers before add_item! NEVER add the same combo twice!
                    (12) Hierarchical menu browsing (ALWAYS use real Qu menu data):
                        - For "what do you have?" or very general queries: Call get_menu_categories() - this instantly returns ALL top-level menu categories (pre-loaded from Qu). List ALL categories conversationally - NEVER say "and more". Read all categories from the response and list them naturally.
                        - For category queries like "what [category name]?": Call get_category_items(category) - this instantly returns all items in that category (pre-loaded from Qu). List 3-5 popular items casually. Don't read the entire list if there are too many.
                        - For specific item queries like "do you have [item name]?": Call query_items with the exact item name for semantic search. Only confirm availability based on query_items results.
                        - IMPORTANT: Category names come directly from Qu API and may change daily. Always use the exact category names returned by get_menu_categories().
                    (13) Order completion flow: After asking about dessert, call submit_order_to_qu, tell them the total price, THEN ask them to drive to the window. Never say "drive to window for your total" - always give the total first.
                    (14) Function calling rules - DO THIS EVERY TIME:
                        (A) When customer orders an item: Call query_items → **ALWAYS USE THE FIRST RESULT** → Call add_item with that itemPathKey
                        (A1) ⚠️ CRITICAL: query_items/query_modifiers return a RANKED list - the FIRST result is the BEST match! ALWAYS use results[0].itemPathKey - NEVER skip to results[1] or results[2]!
                        (A2) ⚠️ CRITICAL - COMBO WITH SIDES/DRINKS IN SAME SENTENCE: When customer orders "Jumbo Jack with curly fries and a coke":
                             CORRECT FLOW:
                             1. query_items("Jumbo Jack") ← Only query the COMBO, NOT the sides/drinks
                             2. add_item(itemPathKey from step 1) ← Add combo FIRST
                             3. query_modifiers("curly fries", parent=itemPathKey from step 2)
                             4. add_modifier(itemId from step 2, itemPathKey from step 3)
                             5. query_modifiers("coca cola", parent=itemPathKey from step 2) ← Use "coca cola" NOT "coke"!
                             6. add_modifier(itemId from step 2, itemPathKey from step 5)
                             
                             WRONG FLOW (DO NOT DO THIS):
                             ❌ query_items("coke") - NO! Use query_modifiers instead
                             ❌ query_items("curly fries") - NO! Use query_modifiers instead
                             ❌ add_item for fries/drinks - NO! Use add_modifier instead
                             
                             Remember: For combo sides/drinks, SKIP query_items entirely. Go straight to query_modifiers + add_modifier!
                        (B) COMBO SPECIAL RULE: After calling add_item for a combo, you MUST ask for side/drink BEFORE doing anything else. Do not call order(), do not ask about dessert, do not move on. Get the side/drink first!
                        (C) When they specify modifiers/sides/drinks for a combo: The combo MUST already be in the order (via add_item) before you can add modifiers. If you've already called add_item for this combo, do NOT call it again!
                        (C1) ⚠️ CRITICAL - CHANGING SIDES/DRINKS: When customer wants to change a side or drink (e.g., "change curly fries to regular fries"):
                             - DO NOT call delete_item to remove the entire combo!
                             - Instead: Call query_modifiers for the new side/drink, then call add_modifier with the new itemPathKey
                             - The system will AUTOMATICALLY replace the old side/drink with the new one
                             - Keep the combo in the order - just add the new modifier!
                             - Note: "Regular fries" are called "French Fries" in the menu. "Fries" variants available: French Fries, Curly Fries, Garlic Fries, Garlic Curly Fries, Halfsies Fries
                             - Example: Customer has combo with curly fries and says "change to regular fries"
                               1. query_modifiers(query="regular fries", parent="47587-56634-105606") or query_modifiers(query="french fries", parent="47587-56634-105606")
                               2. add_modifier(itemId="xxx", itemPathKey=result_from_query_modifiers)
                               3. Done! The old curly fries will be automatically replaced
                             Example for combo sides/drinks when combo is ALREADY ADDED: "Curly fries and a Coke" = 
                             1. query_modifiers("curly fries", parent=itemPathKey from previous add_item)
                             2. add_modifier
                             3. query_modifiers("coca cola", parent=itemPathKey from previous add_item) ← Use "coca cola" NOT "coke"!
                             4. add_modifier
                             Do NOT call query_items or add_item again - the combo is already in the order!
                        (D) CRITICAL FOR COMBOS: The "parent" parameter in query_modifiers MUST be the itemPathKey (EXAMPLE: "47587-56634-105606"), NOT the itemId (UUID like "7e2bb5d9-...").
                        (E) ⚠️ BANNED FOR COMBO SIDES/DRINKS: NEVER use query_items for fries, drinks, or any side when you already have a combo in the order. ALWAYS use query_modifiers with the combo's itemPathKey as parent. query_items will give you standalone items which will be rejected by the system! 
                             - When add_item returns both itemId and itemPathKey, USE THE itemPathKey (the one from add_item response) for query_modifiers.
                             - Example: If add_item returned itemPathKey "47587-56634-105606", call: query_modifiers(query="fries", parent="47587-56634-105606")
                             - IMPORTANT: Use the ACTUAL itemPathKey from add_item response, not this example value!
                        (F) For drinks: Use "Mod -" items (like "Mod - Coca Cola"), not "Flavor Shot -"
                        (F1) ⚠️ CRITICAL - COKE/COCA-COLA CLARIFICATION:
                             - When customer says "coke", "large coke", "regular coke" → query_modifiers with query="coca cola" (NOT "coke")
                             - This will return "Mod - Coca Cola" (the actual drink, NOT "Flavor Shot")
                             - "Diet Coke", "diet" → query_modifiers with query="diet coke"
                             - "Coke Zero", "zero sugar" → query_modifiers with query="coca cola zero"
                             - ALWAYS query for "coca cola" to get "Mod - Coca Cola", NEVER accept "Flavor Shot - Coke/Coke Zero"
                             - Note: "Large" refers to size, not a different drink.
                        (G) Use get_menu_categories() for "what do you have?", get_category_items(category) for category-specific queries
                        (H) EVERY item MUST call add_item. EVERY modifier MUST call add_modifier. No shortcuts!
                        (I) ⚠️ CRITICAL - DESSERTS ARE STANDALONE ITEMS:
                             - Desserts (cakes, shakes, churros, etc.) are NEVER combo modifiers
                             - ALWAYS use query_items → add_item for desserts (same as burgers/sandwiches)
                             - NEVER use query_modifiers or add_modifier for desserts
                             - Example: "Can I get cheesecake?" → query_items("cheesecake") → add_item(itemPathKey)
                             - Example: "Add a shake" → query_items("shake") → add_item(itemPathKey)
                    
                    (15) ⚠️ CRITICAL - COMBO NUMBERS VS itemPathKey:
                         Sometimes, people will order combos by their combo numbers. Here is a mapping of combo numbers to their respective items:
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
                            ]
                         ⚠️ ⚠️ ⚠️ CRITICAL WARNING ⚠️ ⚠️ ⚠️
                         Combo numbers (1, 2, 3, etc.) are ONLY for customer reference!
                         NEVER use combo numbers as itemPathKey in add_item()!
                         
                         CORRECT FLOW when customer orders "Combo #6":
                         1. Call query_items("Jumbo Jack combo") → Get results list → **USE THE FIRST RESULT** (results[0])
                         2. Extract itemPathKey from results[0] (EXAMPLE FORMAT: "47587-56635-99286")
                         3. Call add_item with results[0].itemPathKey - NOT with "6"!
                         
                         itemPathKey format EXAMPLE: "47587-56634-105606" (long string with dashes)
                         NOT: "6" or any single digit!
                         
                         IMPORTANT: itemPathKey values are DYNAMIC and come from query_items.
                         NEVER hardcode itemPathKey values - always use what query_items returns!
                         """,
                "functions": [
                    {
                        "name": "order",
                        "description": "Call this ONLY when the customer explicitly asks to review their order (e.g., 'What's in my order?' or 'Can you repeat that?'). DO NOT call this after adding items - just continue taking the order.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    },
                    {
                        "name": "query_items",
                        "description": "Call this to query standalone menu items from any category. ⚠️ DO NOT use this for combo sides/drinks - use query_modifiers instead! This returns standalone items which cannot be added as modifiers to combos.",
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
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "query_modifiers",
                        "description": "Call this to query the available modifiers on items, such as sauces, sides, toppings, etc. ⚠️ REQUIRED for combo sides/drinks - NEVER use query_items for combo sides/drinks as it will return invalid standalone items. This function returns modifiers that belong to the parent item (like fries that belong to a combo). Always provide the parent itemPathKey. NOTE: For Coke, query 'coca cola' (NOT 'coke') to get 'Mod - Coca Cola' (the actual drink, NOT 'Flavor Shot').",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "A query for the modifier the user is interested in (e.g., 'curly fries', 'coca cola'). For Coke, use 'coca cola' (NOT 'coke') to get 'Mod - Coca Cola'. For Diet Coke, use 'diet coke'."
                                },
                                "parent": {
                                    "type": "string",
                                    "description": "REQUIRED. MUST be the itemPathKey (EXAMPLE format: '47587-56634-105606'), NEVER the itemId (UUID). For combos, use the combo's itemPathKey from add_item response. This value is DYNAMIC - use the actual itemPathKey returned by add_item, not a hardcoded value!"
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "The number of results to return. The default is 5. If it seems like the item might be found if more results are returned, specify a larger value."
                                }
                            },
                            "required": ["query", "parent"]
                        }
                    },
                    {
                        "name": "add_item",
                        "description": "Add an item to the order. When the user has confirmed they want this item added to their order, call this function. Make sure you first obtain the itemPathKey by calling the query_item function before calling this function. IMPORTANT: This returns an object with 'itemId' (UUID) and 'itemPathKey' (EXAMPLE format: '47587-56634-105606'). For COMBOS, save the itemPathKey from the response - you will need it as the 'parent' parameter when calling query_modifiers for sides/drinks. The itemPathKey is DYNAMIC and changes daily with menu refreshes.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "itemPathKey": {
                                    "type": "string",
                                    "description": "The unique item path key identifying the item. Format: '47587-56634-105606' (long string with dashes). NEVER use combo numbers (1, 2, 3, etc.) - only use the itemPathKey from query_items result!"
                                }
                            },
                            "required": ["itemPathKey"]
                        }
                    },
                    {
                        "name": "delete_item",
                        "description": "Deletes an item to the order. Make sure you first obtain the itemId by calling the order function before calling this function.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "itemId": {
                                    "type": "string",
                                    "description": "The unique item id identifying the item in the order."
                                }
                            },
                            "required": ["itemId"]
                        }
                    },
                    {
                        "name": "add_modifier",
                        "description": "Adds a modifier to an item on an order. Make sure you first obtain the itemId of the item and the itemPathKey of the modifier by calling other functions before calling this function.",
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
                            "required": ["itemPathKey", "itemId"]
                        }
                    },
                    {
                        "name": "submit_order_to_qu",
                        "description": "Submit the completed order to Qu API for fulfillment. Call this after the customer confirms they are done ordering and ready to complete their purchase. This will finalize the order in the Qu system.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    },
                    {
                        "name": "get_menu_categories",
                        "description": "Get the top-level menu categories (pre-loaded at startup for fast response). Call this ONLY for general queries like 'what do you have?' or 'what's on the menu?'. Returns a list of all available categories.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    },
                    {
                        "name": "get_category_items",
                        "description": "Get all items for a specific category (pre-loaded at startup for instant response). Call this for category-specific queries when customer asks about a specific category. Use the exact category names from get_menu_categories(). Much faster than query_items for browsing categories.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "description": "The category name to get items for. Use exact category names from get_menu_categories() response (e.g., 'Breakfast', 'Lunch/Dinner', 'Snacks, Sides & Extras', 'Drinks')"
                                }
                            },
                            "required": ["category"]
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
    }

