from django.urls import path
from . import views

urlpatterns = [
    path('message/',  views.chat_message,             name='chat_message'),
    path('history/',  views.chat_history,             name='chat_history'),
    path('reset/',    views.chat_reset,               name='chat_reset'),
    path('analyze/',  views.analyze_project,          name='analyze_project'),
    path('proposal/', views.generate_project_proposal,name='generate_proposal'),
]
