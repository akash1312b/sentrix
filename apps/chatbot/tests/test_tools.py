import pytest

from apps.chatbot.tools import execute_tool


@pytest.mark.django_db
def test_get_stock_level_tool(shop, product, owner_user):
    result = execute_tool(shop=shop, user=owner_user, tool_name="get_stock_level",
                           tool_input={"product_name": "Test Widget"})
    assert result["found"] is True
    assert result["quantity"] == 20


@pytest.mark.django_db
def test_get_stock_level_tool_not_found(shop, product, owner_user):
    result = execute_tool(shop=shop, user=owner_user, tool_name="get_stock_level",
                           tool_input={"product_name": "Nonexistent Product"})
    assert result["found"] is False


@pytest.mark.django_db
def test_adjust_stock_tool_records_sale(shop, product, owner_user):
    result = execute_tool(
        shop=shop, user=owner_user, tool_name="adjust_stock",
        tool_input={"product_name": "Test Widget", "transaction_type": "sale_out", "quantity": 5},
    )
    assert result["success"] is True
    assert result["new_quantity"] == 15


@pytest.mark.django_db
def test_adjust_stock_tool_blocks_overselling(shop, product, owner_user):
    result = execute_tool(
        shop=shop, user=owner_user, tool_name="adjust_stock",
        tool_input={"product_name": "Test Widget", "transaction_type": "sale_out", "quantity": 999},
    )
    assert result["success"] is False
    assert "error" in result


@pytest.mark.django_db
def test_list_low_stock_tool(shop, product, owner_user):
    execute_tool(shop=shop, user=owner_user, tool_name="adjust_stock",
                 tool_input={"product_name": "Test Widget", "transaction_type": "sale_out", "quantity": 16})
    result = execute_tool(shop=shop, user=owner_user, tool_name="list_low_stock_products", tool_input={})
    assert result["count"] == 1
    assert result["products"][0]["name"] == "Test Widget"


@pytest.mark.django_db
def test_create_purchase_order_tool(shop, product, owner_user):
    result = execute_tool(
        shop=shop, user=owner_user, tool_name="create_purchase_order",
        tool_input={"product_name": "Test Widget", "quantity": 25},
    )
    assert result["success"] is True

    from apps.suppliers.models import PurchaseOrder
    po = PurchaseOrder.objects.get(id=result["purchase_order_id"])
    assert po.items.first().quantity == 25
