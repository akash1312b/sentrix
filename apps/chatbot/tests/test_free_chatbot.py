import pytest

from apps.chatbot.services import run_chat_turn
from apps.inventory.models import Product


@pytest.mark.django_db
def test_free_chatbot_greetings(shop, owner_user):
    conversation = [{"role": "user", "content": "Hello!"}]
    reply, history = run_chat_turn(shop=shop, user=owner_user, conversation=conversation)
    assert "Sentrix AI inventory assistant" in reply
    assert len(history) == 2


@pytest.mark.django_db
def test_free_chatbot_stock_query(shop, product, owner_user):
    conversation = [{"role": "user", "content": "How much Test Widget do I have left?"}]
    reply, history = run_chat_turn(shop=shop, user=owner_user, conversation=conversation)
    assert "Test Widget" in reply
    assert "20" in reply


@pytest.mark.django_db
def test_free_chatbot_record_sale(shop, product, owner_user):
    conversation = [{"role": "user", "content": "Sold 4 Test Widget"}]
    reply, history = run_chat_turn(shop=shop, user=owner_user, conversation=conversation)
    assert "Recorded sale of **4**" in reply
    product.refresh_from_db()
    assert product.quantity == 16


@pytest.mark.django_db
def test_free_chatbot_low_stock_list(shop, product, owner_user):
    # Adjust stock to trigger low stock
    product.quantity = 4
    product.save()

    conversation = [{"role": "user", "content": "What is low on stock?"}]
    reply, history = run_chat_turn(shop=shop, user=owner_user, conversation=conversation)
    assert "Test Widget" in reply
    assert "4 left" in reply


@pytest.mark.django_db
def test_free_chatbot_create_purchase_order(shop, product, owner_user):
    conversation = [{"role": "user", "content": "Order 35 Test Widget"}]
    reply, history = run_chat_turn(shop=shop, user=owner_user, conversation=conversation)
    assert "Drafted Purchase Order" in reply
    assert "PO-" in reply


@pytest.mark.django_db
def test_free_chatbot_fallback(shop, owner_user):
    conversation = [{"role": "user", "content": "Random gibberish question 12345"}]
    reply, history = run_chat_turn(shop=shop, user=owner_user, conversation=conversation)
    assert "I couldn't find a product" in reply or "Try asking" in reply
