import pytest
from rest_framework import status


@pytest.mark.django_db
def test_product_list_requires_shop_header(api_client, owner_user, shop, product):
    api_client.force_authenticate(user=owner_user)
    resp = api_client.get("/api/v1/inventory/products/")
    assert resp.status_code == status.HTTP_404_NOT_FOUND  # missing X-Shop-Id


@pytest.mark.django_db
def test_product_list_scoped_to_shop(api_client, owner_user, shop, product):
    api_client.force_authenticate(user=owner_user)
    resp = api_client.get("/api/v1/inventory/products/", HTTP_X_SHOP_ID=str(shop.id))
    assert resp.status_code == status.HTTP_200_OK
    names = [p["name"] for p in resp.data["results"]] if "results" in resp.data else [p["name"] for p in resp.data]
    assert "Test Widget" in names


@pytest.mark.django_db
def test_barcode_lookup(api_client, owner_user, shop, product):
    api_client.force_authenticate(user=owner_user)
    resp = api_client.post(
        "/api/v1/inventory/products/barcode-lookup/",
        {"barcode": product.barcode},
        HTTP_X_SHOP_ID=str(shop.id),
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["sku"] == product.sku


@pytest.mark.django_db
def test_barcode_lookup_not_found(api_client, owner_user, shop, product):
    api_client.force_authenticate(user=owner_user)
    resp = api_client.post(
        "/api/v1/inventory/products/barcode-lookup/",
        {"barcode": "0000000000000"},
        HTTP_X_SHOP_ID=str(shop.id),
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_adjust_stock_endpoint(api_client, owner_user, shop, product):
    api_client.force_authenticate(user=owner_user)
    resp = api_client.post(
        f"/api/v1/inventory/products/{product.id}/adjust-stock/",
        {"transaction_type": "sale_out", "quantity": -5, "note": "counter sale"},
        HTTP_X_SHOP_ID=str(shop.id),
    )
    assert resp.status_code == status.HTTP_201_CREATED
    product.refresh_from_db()
    assert product.quantity == 15


@pytest.mark.django_db
def test_user_cannot_access_other_shops_products(api_client, owner_user, product):
    from apps.accounts.models import Shop

    other_shop = Shop.objects.create(name="Someone Else's Shop")
    api_client.force_authenticate(user=owner_user)
    resp = api_client.get("/api/v1/inventory/products/", HTTP_X_SHOP_ID=str(other_shop.id))
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_sample_data_workflow(api_client, owner_user, shop):
    api_client.force_authenticate(user=owner_user)

    # Initially no sample data
    resp = api_client.get("/api/v1/inventory/products/sample-data/", HTTP_X_SHOP_ID=str(shop.id))
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["loaded"] is False

    # Load sample data
    resp = api_client.post("/api/v1/inventory/products/sample-data/", HTTP_X_SHOP_ID=str(shop.id))
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["loaded"] is True
    assert resp.data["count"] == 10

    # Calling post again returns 409
    resp = api_client.post("/api/v1/inventory/products/sample-data/", HTTP_X_SHOP_ID=str(shop.id))
    assert resp.status_code == status.HTTP_409_CONFLICT

    # Delete sample data
    resp = api_client.delete("/api/v1/inventory/products/sample-data/", HTTP_X_SHOP_ID=str(shop.id))
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["loaded"] is False


@pytest.mark.django_db
def test_import_template_and_csv_import(api_client, owner_user, shop):
    from io import BytesIO

    api_client.force_authenticate(user=owner_user)

    # Test template download
    resp = api_client.get("/api/v1/inventory/products/import-template/", HTTP_X_SHOP_ID=str(shop.id))
    assert resp.status_code == status.HTTP_200_OK
    assert "text/csv" in resp["Content-Type"]

    # Test CSV upload with valid and problem rows
    csv_content = (
        "Product Name,Selling Price,Cost Price,SKU,Barcode,Category,Stock Quantity\n"
        "Sugar 1kg,50.00,42.00,SUG-1K,8901234567890,Groceries,20\n"
        "Salt 1kg,,15.00,SLT-1K,,Groceries,10\n"  # Problem: empty selling price
    ).encode("utf-8")

    file_obj = BytesIO(csv_content)
    file_obj.name = "test_import.csv"

    resp = api_client.post(
        "/api/v1/inventory/products/import/",
        {"file": file_obj},
        format="multipart",
        HTTP_X_SHOP_ID=str(shop.id),
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["created"] == 1
    assert resp.data["skipped"] == 1
    assert len(resp.data["problems"]) == 1
    assert resp.data["problems"][0]["row"] == 3

