from django.urls import path

from chat import views

app_name = "chat"

urlpatterns = [
    path("chats/", views.chat_list, name="chat-list"),
    path("chats/<int:pk>/", views.chat_detail, name="chat-detail"),
    path("chats/<int:pk>/messages/", views.chat_send_message, name="chat-send-message"),
]
