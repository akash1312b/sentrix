from django.conf import settings
from django.db import models

from apps.core.models import ShopScopedModel


class ChatSession(ShopScopedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_sessions")
    title = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title or f"Session {str(self.id)[:8]}"


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"
        TOOL = "tool", "Tool result"

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()
    tool_name = models.CharField(max_length=100, blank=True)
    tool_input = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"
