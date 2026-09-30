from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import ShopScopedViewSetMixin

from .models import ChatMessage, ChatSession
from .serializers import ChatRequestSerializer, ChatSessionSerializer
from .services import run_chat_turn


class ChatView(ShopScopedViewSetMixin, APIView):
    """
    POST { "message": "...", "session_id": "<optional>" }
    ->  { "session_id": "...", "reply": "..." }

    Stateless from the client's point of view — the full conversation
    history is reloaded from ChatMessage rows on every call, so any
    frontend (web, mobile, even WhatsApp) can drive the same session.
    """
    throttle_scope = "chatbot"

    def get_queryset(self):
        return ChatSession.objects.all()

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        session = None
        if data.get("session_id"):
            session = self.get_queryset().filter(pk=data["session_id"]).first()
        if not session:
            session = ChatSession.objects.create(
                shop=request.shop, user=request.user,
                title=data["message"][:60],
            )

        ChatMessage.objects.create(session=session, role="user", content=data["message"])

        history = [
            {"role": m.role, "content": m.content}
            for m in session.messages.filter(role__in=["user", "assistant"]).order_by("created_at")
        ]

        reply_text, _full_conversation = run_chat_turn(
            shop=request.shop, user=request.user, conversation=history,
        )

        ChatMessage.objects.create(session=session, role="assistant", content=reply_text)

        return Response(
            {"session_id": str(session.id), "reply": reply_text},
            status=status.HTTP_200_OK,
        )


class ChatSessionListView(ShopScopedViewSetMixin, APIView):
    def get_queryset(self):
        return ChatSession.objects.all()

    def get(self, request):
        sessions = self.get_queryset().filter(user=request.user)
        return Response(ChatSessionSerializer(sessions, many=True).data)
