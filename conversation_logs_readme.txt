================================================================================
    CONVERSATION LOGS - Quick Guide
================================================================================

## What Are Conversation Logs?

Every conversation with the voice agent is now automatically logged to a file
with timestamps, function calls, and detailed data.

================================================================================
LOG FILE LOCATION
================================================================================

Local (your machine):
  ~/Desktop/CODE/JITB/dg-compat-lab/conversation_logs/

EC2 Server:
  ~/dg-compat-lab/conversation_logs/

File naming format:
  conversation_YYYYMMDD_HHMMSS.log
  
Example:
  conversation_20251118_214530.log


================================================================================
WHAT'S LOGGED
================================================================================

1. Conversation Start/End
   - Timestamp when conversation begins
   - Timestamp when conversation ends

2. All Function Calls
   - Function name
   - Parameters passed
   - Data returned (in JSON format)
   - Timestamp for each call

3. Order Details
   - Items added/removed
   - Modifiers added
   - Price calculations
   - Final order submission


================================================================================
LOG FILE FORMAT
================================================================================

Each log file contains:

================================================================================
JACK IN THE BOX VOICE AGENT - CONVERSATION LOG
Started: 2025-11-18 14:45:30
================================================================================

[2025-11-18 14:45:30.123] CONVERSATION_START - New conversation initiated

[2025-11-18 14:45:35.456] FUNCTION_CALL - query_items
    Data: {
        "query": "Jumbo Jack",
        "limit": 5
    }

[2025-11-18 14:45:36.789] FUNCTION_CALL - add_item
    Data: {
        "itemPathKey": "47587-56634-105606"
    }

[2025-11-18 14:45:40.012] FUNCTION_CALL - query_modifiers
    Data: {
        "query": "curly fries",
        "parent": "47587-56634-105606",
        "limit": 5
    }

[2025-11-18 14:45:45.345] FUNCTION_CALL - submit_order_to_qu
    Data: {
        "items_count": 2
    }

[2025-11-18 14:46:00.678] CONVERSATION_END - Conversation ended

================================================================================
Ended: 2025-11-18 14:46:00
================================================================================


================================================================================
HOW TO VIEW LOGS
================================================================================

On Your Local Machine:
  cd ~/Desktop/CODE/JITB/dg-compat-lab/conversation_logs
  ls -lt                          # List logs by newest first
  cat conversation_*.log          # View most recent log
  tail -f conversation_*.log      # Follow a log in real-time

On EC2 Server:
  ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103
  cd ~/dg-compat-lab/conversation_logs
  ls -lt                          # List logs by newest first
  cat conversation_*.log          # View most recent log
  tail -100 conversation_*.log    # View last 100 lines

View Most Recent Log (one command):
  ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 "cat ~/dg-compat-lab/conversation_logs/conversation_*.log | tail -100"


================================================================================
DEBUGGING WITH LOGS
================================================================================

1. Check Order Total Issue:
   - Look for "submit_order_to_qu" function call
   - See the "Calculating order total" section in server logs
   - Compare item prices in log vs UI

2. Check Function Call Sequence:
   - Look at the order of function calls
   - Verify query_items → add_item flow
   - Verify query_modifiers → add_modifier flow

3. Check What Items Were Added:
   - Look for "add_item" calls with itemPathKey
   - Look for "add_modifier" calls with modifier itemPathKey
   - Check the data JSON for each call

4. Find Pricing Issues:
   - Search for "💰" in logs (pricing info)
   - Look for "included in combo" vs "extra charge"
   - Check if modifiers are being charged correctly


================================================================================
EXAMPLE: DEBUGGING TOTAL MISMATCH
================================================================================

Problem: Agent said $37.74, UI showed $18.97

Steps to debug:
1. Find the conversation log for that session
2. Look for "submit_order_to_qu" timestamp
3. Check server logs around that timestamp:
   ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 "sudo journalctl -u jitb-web --since '14:45:00' | grep -A 30 '💰 Calculating'"
4. Compare what was calculated vs what was displayed


================================================================================
CLEANUP OLD LOGS
================================================================================

Delete logs older than 7 days (on server):
  ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 "find ~/dg-compat-lab/conversation_logs -name '*.log' -mtime +7 -delete"

Delete all logs (on server):
  ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 "rm ~/dg-compat-lab/conversation_logs/*.log"


================================================================================
NOTES
================================================================================

- Logs are created when "Start Conversation" is clicked
- Logs are closed when "End Conversation" is clicked or connection drops
- Each conversation gets its own unique log file
- Logs are NOT automatically deleted (manual cleanup required)
- Log files are plain text (easy to grep/search)


================================================================================
END OF GUIDE
================================================================================

