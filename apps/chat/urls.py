from django.urls import path
from . import views

urlpatterns = [
    path('message/',  views.chat_message, name='chat_message'),
    path('history/',  views.chat_history, name='chat_history'),
    path('reset/',    views.chat_reset,   name='chat_reset'),
    path('proposal/', views.get_proposal, name='get_proposal'),
]
