from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Membership, Shop

User = get_user_model()


class ShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = [
            "id", "name", "address", "phone_number", "currency",
            "low_stock_threshold_default", "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class MembershipSerializer(serializers.ModelSerializer):
    shop = ShopSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "shop", "role", "created_at"]


class UserSerializer(serializers.ModelSerializer):
    memberships = MembershipSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "phone_number", "receive_email_alerts", "receive_sms_alerts",
            "memberships",
        ]
        read_only_fields = ["id"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    shop_name = serializers.CharField(write_only=True, max_length=255)

    class Meta:
        model = User
        fields = ["username", "email", "password", "first_name", "last_name", "shop_name"]

    def create(self, validated_data):
        shop_name = validated_data.pop("shop_name")
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()

        shop = Shop.objects.create(name=shop_name)
        Membership.objects.create(user=user, shop=shop, role=Membership.Role.OWNER)
        return user
