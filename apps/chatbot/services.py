"""
Thin wrapper implementing an agentic tool-use loop against whichever LLM
provider is configured: send the conversation -> if the model wants a
tool, run it locally -> feed the result back -> repeat until the model
returns a plain text answer.
"""
import json
import logging

from django.conf import settings

from .tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger("apps.chatbot")

SYSTEM_PROMPT = """\
You are the Sentrix assistant, embedded in a small shop's inventory
management dashboard. You help the shop owner or staff check stock
levels, record sales/purchases, and manage suppliers — entirely through
conversation.

Rules:
- Never state a stock quantity, sales figure, or forecast unless it came
  from a tool call in this conversation. If you don't know, call a tool.
- For anything that changes data (adjust_stock, create_purchase_order),
  briefly confirm what you're about to do in your reply.
- Keep answers short and practical — this is a busy shop owner, not a
  chat for its own sake.
"""

MAX_TOOL_ITERATIONS = 5


def _openai_style_tools() -> list[dict]:
    """Convert Anthropic-style tool definitions into the OpenAI-compatible
    shape that Groq expects."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in TOOL_DEFINITIONS
    ]


import os
import re
import urllib.request
import urllib.error

def run_chat_turn(*, shop, user, conversation: list[dict]) -> tuple[str, list[dict]]:
    groq_key = getattr(settings, "GROQ_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")
    provider = getattr(settings, "CHATBOT_PROVIDER", "free").lower()
    
    # If Groq is explicitly chosen or GROQ_API_KEY is supplied, attempt Groq first
    if provider == "groq" or (provider == "free" and groq_key):
        try:
            return _run_chat_turn_groq(shop=shop, user=user, conversation=conversation)
        except Exception as exc:
            logger.warning("Groq provider execution failed (%s), seamlessly falling back to free engine.", exc)
            reply, hist = _run_chat_turn_free(shop=shop, user=user, conversation=conversation)
            if provider == "groq":
                notice = "*(Note: Groq Cloud API was unavailable, answered via Sentrix smart retail assistant)*\n\n"
                return notice + reply, hist
            return reply, hist
    elif provider == "ollama":
        try:
            return _run_chat_turn_ollama(shop=shop, user=user, conversation=conversation)
        except Exception as exc:
            logger.warning("Ollama provider failed (%s), falling back to free engine.", exc)
            reply, hist = _run_chat_turn_free(shop=shop, user=user, conversation=conversation)
            notice = "*(Note: Ollama was unavailable at localhost:11434, answered via built-in assistant)*\n\n"
            return notice + reply, hist
    elif provider == "anthropic":
        try:
            return _run_chat_turn_anthropic(shop=shop, user=user, conversation=conversation)
        except Exception as exc:
            logger.warning("Anthropic provider failed (%s), falling back to free engine.", exc)
            reply, hist = _run_chat_turn_free(shop=shop, user=user, conversation=conversation)
            notice = "*(Note: Anthropic API was unconfigured, answered via built-in assistant)*\n\n"
            return notice + reply, hist

    return _run_chat_turn_free(shop=shop, user=user, conversation=conversation)


def _run_chat_turn_free(*, shop, user, conversation: list[dict]) -> tuple[str, list[dict]]:
    """
    100% Free, zero-API-key built-in natural language engine.
    Parses intent directly from conversation, executes tools,
    and returns grounded, concise answers without any external cost.
    """
    latest_msg = ""
    for msg in reversed(conversation):
        if msg.get("role") == "user":
            latest_msg = msg.get("content", "").strip()
            break

    query = latest_msg.lower()
    clean_query = re.sub(r"[^\w\s\-\.]", " ", query).strip()

    messages = list(conversation)
    reply = ""

    # 1. Greetings & Help
    if re.search(r"^(hi|hello|hey|help|commands|what can you do|about)\b", clean_query) or not clean_query:
        reply = (
            f"Hello! I am your Sentrix AI inventory assistant for **{shop.name}**.\n\n"
            "Here is what you can ask me to do for free:\n"
            "• **Check stock**: *'How much Tata Salt left?'* or *'Stock of Maggi'*\n"
            "• **Record sales**: *'Sold 5 Maggi'* or *'Customer bought 2 Amul Butter'*\n"
            "• **Stock in / Restock**: *'Add 20 Parle-G'* or *'Received 10 Colgate'*\n"
            "• **Low stock alerts**: *'What items are low on stock?'*\n"
            "• **Stockout forecast**: *'When will Maggi run out?'*\n"
            "• **Purchase orders**: *'Order 30 Tata Salt'*"
        )

    # 2. Low stock check
    elif re.search(r"\b(low\s*(?:on\s*)?stock|out\s*of\s*stock|shortage|running\s*low|stock\s*low|low\s*items|reorder\s*needed)\b", clean_query):
        result = execute_tool(shop=shop, user=user, tool_name="list_low_stock_products", tool_input={})
        count = result.get("count", 0)
        if count == 0:
            reply = "All products currently have healthy stock levels above their reorder thresholds."
        else:
            lines = [f"Found **{count}** product(s) at or below reorder threshold:"]
            for p in result.get("products", []):
                lines.append(f"• **{p['name']}** ({p['sku']}): {p['quantity']} left (threshold: {p['reorder_threshold']})")
            lines.append("\nYou can say *'Order [qty] [product]'* to auto-draft a purchase order.")
            reply = "\n".join(lines)

    # 3. Stockout / Run-out forecast
    elif re.search(r"\b(when will|days until stockout|stockout of|forecast|estimate stockout|burn rate|how long will|run out)\b", clean_query):
        # Extract product name
        prod_candidate = re.sub(r"^.*?\b(when will|days until stockout(?: for)?|stockout of|forecast|estimate stockout(?: for)?|burn rate(?: for)?|how long will|estimate)\s+", "", clean_query)
        prod_candidate = re.sub(r"\s+(run out|last|stockout|take)\b.*$", "", prod_candidate).strip()
        
        if not prod_candidate:
            reply = "Which product would you like to estimate stockout for? (e.g. *'When will Maggi run out?'*)"
        else:
            result = execute_tool(shop=shop, user=user, tool_name="estimate_stockout", tool_input={"product_name": prod_candidate})
            if not result.get("found"):
                reply = f"Could not find any product matching '{prod_candidate}' in {shop.name}."
            elif result.get("days_until_stockout") is None:
                reply = f"No recent sales found for **{result['product_name']}** over the past 30 days to calculate a burn rate."
            else:
                reply = (
                    f"Based on recent sales velocity, **{result['product_name']}** "
                    f"is estimated to run out in **{result['days_until_stockout']} days**."
                )

    # 4. Draft Purchase Order
    elif re.search(r"\b(order|reorder|create po|draft po|purchase order)\b", clean_query):
        qty_match = re.search(r"\b(?:order|reorder|create po|draft po|purchase order)\s+(\d+)\s+(?:units?\s+of\s+)?(.+)", clean_query)
        if not qty_match:
            qty_match = re.search(r"\b(?:order|reorder|create po|draft po|purchase order)\s+(?:for\s+)?(.+?)\s+(\d+)\b", clean_query)
            if qty_match:
                prod_name = qty_match.group(1).strip()
                qty = int(qty_match.group(2))
            else:
                prod_name, qty = "", 0
        else:
            qty = int(qty_match.group(1))
            prod_name = qty_match.group(2).strip()

        if not prod_name or qty <= 0:
            reply = "Please specify product and quantity to reorder (e.g. *'Order 25 Tata Salt'*)."
        else:
            result = execute_tool(shop=shop, user=user, tool_name="create_purchase_order", tool_input={"product_name": prod_name, "quantity": qty})
            if result.get("success"):
                reply = (
                    f"Drafted Purchase Order **PO-{result['purchase_order_id'][:8]}** for {qty} units of **{prod_name}**.\n"
                    f"Status: **{result['status'].title()}** (Awaiting owner approval)."
                )
            else:
                reply = f"Could not create purchase order: {result.get('error', 'Unknown error')}."

    # 5. Stock Adjustments (Sale out, purchase in, damage, return)
    elif re.search(r"\b(sold|sell|sale|add|restock|received?|damaged?|waste|expired?|returned?)\b", clean_query):
        txn_type = "sale_out"
        if re.search(r"\b(add|restock|received?)\b", clean_query):
            txn_type = "purchase_in"
        elif re.search(r"\b(damaged?|waste|expired?)\b", clean_query):
            txn_type = "damage_out"
        elif re.search(r"\b(returned?)\b", clean_query):
            txn_type = "return_in"

        qty_match = re.search(r"\b(?:sold|sell|sale|add|restock|received?|damaged?|waste|expired?|returned?)\s+(\d+)\s+(?:units?\s+of\s+)?(.+)", clean_query)
        if not qty_match:
            qty_match = re.search(r"\b(?:sold|sell|sale|add|restock|received?|damaged?|waste|expired?|returned?)\s+(?:for\s+)?(.+?)\s+(\d+)\b", clean_query)
            if qty_match:
                prod_name = qty_match.group(1).strip()
                qty = int(qty_match.group(2))
            else:
                prod_name, qty = "", 0
        else:
            qty = int(qty_match.group(1))
            prod_name = qty_match.group(2).strip()

        # Remove trailing words like "units", "items"
        prod_name = re.sub(r"\s+(?:units?|packets?|boxes?|pieces?)$", "", prod_name).strip()

        if not prod_name or qty <= 0:
            reply = "Please specify a valid quantity and product (e.g. *'Sold 3 Tata Salt'* or *'Add 10 Maggi'*)."
        else:
            result = execute_tool(
                shop=shop, user=user, tool_name="adjust_stock",
                tool_input={
                    "product_name": prod_name,
                    "transaction_type": txn_type,
                    "quantity": qty,
                    "note": f"Recorded via Free Assistant",
                },
            )
            if result.get("success"):
                action_word = {
                    "sale_out": "Recorded sale of",
                    "purchase_in": "Added stock of",
                    "damage_out": "Marked damaged",
                    "return_in": "Recorded return of",
                }.get(txn_type, "Adjusted")
                reply = f"{action_word} **{qty}** unit(s) for **{result['product_name']}**. New stock balance: **{result['new_quantity']}**."
            else:
                reply = f"Stock update failed: {result.get('error')}."

    # 6. Stock Check / Lookup
    else:
        # Check if query matches "how much ...", "stock of ...", etc.
        lookup_name = re.sub(r"^.*?\b(how much|how many|quantity of|stock of|check stock of|check stock for|stock for|check|find|lookup)\s+", "", clean_query)
        lookup_name = re.sub(r"\s+(left|in stock|available|do i have|we have)\b.*$", "", lookup_name).strip()
        if not lookup_name:
            lookup_name = clean_query

        result = execute_tool(shop=shop, user=user, tool_name="get_stock_level", tool_input={"product_name": lookup_name})
        if result.get("found"):
            status_text = "⚠️ Low stock" if result.get("is_low_stock") else "✅ Healthy"
            reply = (
                f"**{result['product_name']}** ({result['sku']}):\n"
                f"• Current Stock: **{result['quantity']}** units ({status_text})\n"
                f"• Reorder Threshold: **{result['reorder_threshold']}** units"
            )
        else:
            reply = (
                f"I couldn't find a product matching '{latest_msg}'.\n\n"
                "Try asking:\n"
                "• *'How much Tata Salt?'*\n"
                "• *'Show low stock items'*\n"
                "• *'Sold 2 Maggi'* or *'Add 10 Butter'*\n"
                "• *'When will Tata Salt run out?'*"
            )

    messages.append({"role": "assistant", "content": reply})
    return reply, messages


def _run_chat_turn_ollama(*, shop, user, conversation: list[dict]) -> tuple[str, list[dict]]:
    """
    Connects to a locally running Ollama instance at OLLAMA_BASE_URL (http://localhost:11434).
    Uses Ollama's OpenAI-compatible /v1/chat/completions endpoint.
    """
    base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = getattr(settings, "OLLAMA_MODEL", "llama3.2")
    tools = _openai_style_tools()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(conversation)

    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "stream": False,
    }
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=req_data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        res = json.loads(resp.read().decode("utf-8"))

    msg = res["choices"][0]["message"]
    tool_calls = msg.get("tool_calls")
    if not tool_calls:
        return msg.get("content", ""), conversation + [{"role": "assistant", "content": msg.get("content", "")}]

    # Handle tool calls
    for tc in tool_calls:
        func = tc["function"]
        args = json.loads(func["arguments"]) if isinstance(func["arguments"], str) else func["arguments"]
        tool_res = execute_tool(shop=shop, user=user, tool_name=func["name"], tool_input=args)
        messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(tool_res, default=str)})

    # Follow up turn for final response
    req_data2 = json.dumps({"model": model, "messages": messages, "stream": False}).encode("utf-8")
    req2 = urllib.request.Request(f"{base_url}/v1/chat/completions", data=req_data2, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req2, timeout=15) as resp2:
        res2 = json.loads(resp2.read().decode("utf-8"))
    final_text = res2["choices"][0]["message"].get("content", "")
    return final_text, conversation + [{"role": "assistant", "content": final_text}]


def _run_chat_turn_anthropic(*, shop, user, conversation: list[dict]) -> tuple[str, list[dict]]:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    messages = list(conversation)

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        tool_uses = [block for block in response.content if block.type == "tool_use"]

        if not tool_uses:
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            )
            messages.append({"role": "assistant", "content": response.content})
            return final_text, messages

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tool_use in tool_uses:
            logger.info("Chatbot invoking tool %s(%s)", tool_use.name, tool_use.input)
            result = execute_tool(
                shop=shop, user=user, tool_name=tool_use.name, tool_input=tool_use.input,
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": str(result),
            })
        messages.append({"role": "user", "content": tool_results})

    return (
        "I wasn't able to finish that after several steps — could you rephrase or "
        "check the dashboard directly?",
        messages,
    )


def _run_chat_turn_groq(*, shop, user, conversation: list[dict]) -> tuple[str, list[dict]]:
    """
    Groq's API is OpenAI-compatible: tool calls arrive as
    message.tool_calls (each with a JSON-string .function.arguments),
    and tool results are fed back as role="tool" messages keyed by
    tool_call_id.
    """
    from groq import Groq

    api_key = getattr(settings, "GROQ_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not configured.")

    model_name = getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
    client = Groq(api_key=api_key)
    tools = _openai_style_tools()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(conversation)

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=1024,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            messages.append({"role": "assistant", "content": message.content or ""})
            return message.content or "", messages[1:]

        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in message.tool_calls
            ],
        })

        for tool_call in message.tool_calls:
            try:
                tool_input = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_input = {}
            logger.info("Chatbot invoking tool %s(%s)", tool_call.function.name, tool_input)
            result = execute_tool(
                shop=shop, user=user, tool_name=tool_call.function.name, tool_input=tool_input,
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, default=str),
            })

    return (
        "I wasn't able to finish that after several steps — could you rephrase or "
        "check the dashboard directly?",
        messages[1:],
    )