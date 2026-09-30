from rest_framework import serializers

from .models import ChatMessage, ChatSession


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "role", "content", "tool_name", "tool_input", "created_at"]


class ChatSessionSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = ChatSession
        fields = ["id", "title", "messages", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ChatRequestSerializer(serializers.Serializer):
    session_id = serializers.UUIDField(required=False)
    message = serializers.CharField()
