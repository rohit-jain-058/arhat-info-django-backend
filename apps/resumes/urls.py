# apps/resumes/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('',           views.list_resumes,  name='resume_list'),
    path('upload/',    views.upload_resume, name='resume_upload'),
    path('<int:pk>/',  views.get_resume,    name='resume_detail'),
    path('<int:pk>/update/',  views.update_resume,  name='resume_update'),
    path('<int:pk>/delete/',  views.delete_resume,  name='resume_delete'),
    path('<int:pk>/reparse/', views.reparse_resume, name='resume_reparse'),
]
