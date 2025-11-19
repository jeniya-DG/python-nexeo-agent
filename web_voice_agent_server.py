"""
Web Voice Agent Server - FastAPI backend for browser-based voice agent
Run with: uvicorn web_voice_agent_server:app --host 0.0.0.0 --port 8000
"""

import os
import asyncio
import json
import time
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import websockets

# Import Jack in the Box function handlers
import jitb_functions
from jitb_functions import FUNCTION_MAP, load_menu_categories

# Import shared agent configuration
from agent_config import get_agent_settings, MIC_SR, SPK_SR

# Import latency tracking
from latency_tracker import start_timer, end_timer

load_dotenv()

DG_KEY = os.getenv("DEEPGRAM_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
DG_URL = "wss://agent.deepgram.com/v1/agent/converse"

app = FastAPI(title="Jack in the Box Voice Agent")

# Load menu data at startup
@app.on_event("startup")
async def startup_event():
    load_menu_categories()
    print("✅ Menu categories loaded")

# Serve the HTML page - Production
@app.get("/")
async def get():
    with open("web_voice_agent_ui.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

# Serve favicon
@app.get("/favicon.ico")
async def favicon():
    return FileResponse("jack-in-the-box-1-icon.ico", media_type="image/x-icon")

@app.get("/jack-in-the-box-1-icon.ico")
async def favicon_ico():
    return FileResponse("jack-in-the-box-1-icon.ico", media_type="image/x-icon")

@app.get("/jack-in-the-box-1-icon.svg")
async def favicon_svg():
    return FileResponse("jack-in-the-box-1-icon.svg", media_type="image/svg+xml")

# Development environment - for testing new changes
@app.get("/dev")
async def get_dev():
    with open("web_voice_agent_ui_dev.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

# Test environment - stable version for testers
@app.get("/test")
async def get_test():
    with open("web_voice_agent_ui_test.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

# Menu endpoint - returns menu with prices for UI display
@app.get("/menu")
async def get_menu():
    """Get full menu with prices from Qu API via Rust backend"""
    import jitb_functions
    import os
    from datetime import datetime
    
    # Build menu with real prices
    menu_with_prices = {}
    
    try:
        cached_menu = jitb_functions.cached_menu
        QU_PRICES = jitb_functions.QU_PRICES
        
        for category, items in cached_menu.items():
            menu_with_prices[category] = []
            
            # Ensure items is a list
            if not isinstance(items, list):
                continue
                
            for item in items:
                item_path_key = item.get("itemPathKey")
                item_name = item.get("name", "Unknown")
                
                # Skip modifiers - they're not standalone menu items
                if item_name.startswith("Mod -") or item_name.startswith("Modifier -"):
                    continue
                
                # Get real Qu price
                price = QU_PRICES.get(item_path_key, 0.0)
                
                # Skip items with $0.00 price (system/internal items)
                if price > 0:
                    menu_with_prices[category].append({
                        "name": item_name,
                        "price": float(price) if price else 0.0,
                        "itemPathKey": item_path_key
                    })
        
        # Remove empty categories
        menu_with_prices = {k: v for k, v in menu_with_prices.items() if v}
        
        # Add metadata
        location_id = os.getenv("LOCATION_ID", "4776")
        timestamp = datetime.now().isoformat()
        
        return {
            "metadata": {
                "location_id": location_id,
                "timestamp": timestamp,
                "total_items": sum(len(items) for items in menu_with_prices.values()),
                "categories": list(menu_with_prices.keys())
            },
            "menu": menu_with_prices
        }
    except Exception as e:
        print(f"Error in /menu endpoint: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

# Promote dev to test - copy dev version to test
@app.post("/promote-to-test")
async def promote_to_test():
    """Copy the dev version to test environment"""
    try:
        import shutil
        shutil.copy("web_voice_agent_ui_dev.html", "web_voice_agent_ui_test.html")
        return {
            "success": True, 
            "message": "Successfully promoted dev to test!",
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# WebSocket endpoint for browser clients
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🌐 Browser client connected")
    
    # Start conversation log
    jitb_functions.start_conversation_log()
    
    # Connect to Deepgram
    try:
        async with websockets.connect(
            DG_URL,
            extra_headers=[
                ("Authorization", f"Token {DG_KEY}"),
                ("X-OpenAI-API-Key", OPENAI_KEY)
            ]
        ) as dg_ws:
            print("✅ Connected to Deepgram")
            
            # Wait for welcome message
            welcome_msg = await dg_ws.recv()
            welcome_data = json.loads(welcome_msg)
            print(f"📩 Deepgram: {welcome_data.get('type')}")
            
            # Send welcome to browser
            await websocket.send_json({"type": "connected", "message": "Connected to voice agent"})
            
            # Configure the agent using shared configuration
            settings = get_agent_settings(mic_sample_rate=MIC_SR, speaker_sample_rate=SPK_SR)
            
            await dg_ws.send(json.dumps(settings))
            print("⚙️  Settings sent to Deepgram")
            
            # Wait for settings confirmation
            settings_msg = await dg_ws.recv()
            settings_data = json.loads(settings_msg)
            msg_type = settings_data.get('type')
            print(f"📩 Settings response: {msg_type}")
            
            if msg_type == "Error":
                print(f"❌ Settings Error: {json.dumps(settings_data, indent=2)}")
                await websocket.send_json({"type": "error", "message": "Failed to configure agent"})
                return
            
            # Send ready signal to browser
            await websocket.send_json({"type": "ready", "message": "Agent ready"})
            print("✅ Agent ready for conversation")
            
            # Shared flag to signal disconnection
            stop_relay = asyncio.Event()
            
            # Task to receive from browser and forward to Deepgram
            last_audio_time = None
            async def browser_to_deepgram():
                nonlocal last_audio_time
                try:
                    while not stop_relay.is_set():
                        data = await websocket.receive()
                        
                        if "bytes" in data:
                            # Audio data from browser - track when user starts speaking
                            if last_audio_time is None:
                                start_timer("user_speech")
                                last_audio_time = time.time()
                            if not stop_relay.is_set():
                                await dg_ws.send(data["bytes"])
                        elif "text" in data:
                            # Control messages from browser
                            msg = json.loads(data["text"])
                            if msg.get("type") == "ping":
                                await websocket.send_json({"type": "pong"})
                
                except (WebSocketDisconnect, RuntimeError) as e:
                    print("🌐 Browser disconnected")
                    stop_relay.set()
                except Exception as e:
                    if not stop_relay.is_set():
                        print(f"❌ Browser→Deepgram error: {e}")
                    stop_relay.set()
            
            # Task to receive from Deepgram and forward to browser
            async def deepgram_to_browser():
                nonlocal last_audio_time
                try:
                    async for msg in dg_ws:
                        if stop_relay.is_set():
                            break
                            
                        if isinstance(msg, bytes):
                            # Audio data from agent
                            try:
                                await websocket.send_bytes(msg)
                            except (RuntimeError, Exception) as e:
                                # Browser disconnected mid-send
                                stop_relay.set()
                                break
                        else:
                            # JSON message
                            try:
                                data = json.loads(msg)
                                msg_type = data.get("type")
                                
                                # Track agent response time
                                if msg_type == "UserStartedSpeaking":
                                    # User finished speaking, agent is processing
                                    if last_audio_time:
                                        end_timer("user_speech", {"duration_sec": round(time.time() - last_audio_time, 2)})
                                        last_audio_time = None
                                    start_timer("deepgram_response")
                                
                                elif msg_type in ["AgentAudioDone", "AgentThinking"]:
                                    # Agent finished responding
                                    end_timer("deepgram_response", {"type": msg_type})
                                
                                # Handle function calls
                                if msg_type == "FunctionCallRequest":
                                    start_timer("function_call_total")
                                    print(f"🔧 Function call request")
                                    
                                    for func_call in data.get("functions", []):
                                        func_id = func_call.get("id")
                                        func_name = func_call.get("name")
                                        func_args_str = func_call.get("arguments", "{}")
                                        
                                        print(f"   → Calling {func_name}({func_args_str})")
                                        
                                        # Parse arguments
                                        try:
                                            func_args = json.loads(func_args_str)
                                        except:
                                            func_args = {}
                                        
                                        # Execute function
                                        func = FUNCTION_MAP.get(func_name)
                                        if func:
                                            try:
                                                loop = asyncio.get_event_loop()
                                                result = await loop.run_in_executor(
                                                    None,
                                                    lambda: func(**func_args)
                                                )
                                                print(f"   ✓ Result: {result[:100]}..." if len(result) > 100 else f"   ✓ Result: {result}")
                                            except Exception as e:
                                                result = json.dumps({"error": str(e), "success": False})
                                                print(f"   ✗ Error: {e}")
                                        else:
                                            result = json.dumps({"error": f"Function '{func_name}' not found", "success": False})
                                            print(f"   ✗ Function not found")
                                        
                                        # Send response to Deepgram
                                        if not stop_relay.is_set():
                                            response = {
                                                "type": "FunctionCallResponse",
                                                "id": func_id,
                                                "name": func_name,
                                                "content": result
                                            }
                                            await dg_ws.send(json.dumps(response))
                                            
                                            # ALSO send to browser for order display updates
                                            try:
                                                await websocket.send_json(response)
                                            except (RuntimeError, Exception):
                                                # Browser disconnected
                                                stop_relay.set()
                                                break
                                    
                                    end_timer("function_call_total", {"function": func_name if 'func_name' in locals() else "unknown"})
                                
                                # Forward all messages to browser
                                if not stop_relay.is_set():
                                    try:
                                        await websocket.send_json(data)
                                    except (RuntimeError, Exception):
                                        # Browser disconnected
                                        stop_relay.set()
                                        break
                                
                            except json.JSONDecodeError:
                                pass
                
                except Exception as e:
                    if not stop_relay.is_set():
                        print(f"❌ Deepgram→Browser error: {e}")
                    stop_relay.set()
            
            # Run both relay tasks and handle their completion
            await asyncio.gather(
                browser_to_deepgram(),
                deepgram_to_browser(),
                return_exceptions=True
            )
            
            print("✅ Connection closed gracefully")
    
    except Exception as e:
        print(f"❌ Connection error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
    
    finally:
        # End conversation log
        jitb_functions.end_conversation_log()
        print("🔚 Conversation ended")

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Jack in the Box Voice Agent Server...")
    print("📍 Server will be available at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

