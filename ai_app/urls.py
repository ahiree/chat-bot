from django.urls import path
from . import views
urlpatterns = [
    # Authentication URLs
    path('register/', views.register_page, name='register_page'),
    path('login/', views.login_page, name='login_page'),
    path('api/register/', views.register_user, name='register_user'),
    path('api/login/', views.login_user, name='login_user'),
    path('api/logout/', views.logout_user, name='logout_user'),

    # Chat Page
    path('chat/', views.chat_page, name='chat_page'),  # NEW URL
    path('', views.chat_page),  # optional: keep homepage same

    # Chat APIs
    path('api/chat/sessions/create/', views.create_chat_session),
    path('api/chat/sessions/', views.get_chat_sessions),
    path('api/chat/sessions/<uuid:session_id>/', views.get_chat_history),
    path('api/chat/sessions/<uuid:session_id>/title/', views.update_chat_title),
    path('api/chat/sessions/<uuid:session_id>/delete/', views.delete_chat_session),

    # AI Chat
    path('api/chat/', views.ai_chat),

    # Document Upload
    path('api/upload-document/', views.upload_document),
]