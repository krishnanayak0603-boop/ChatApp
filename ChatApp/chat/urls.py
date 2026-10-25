from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("logout/", views.logout_view, name="logout"),
    path("", views.room_list, name="room_list"),
    path("signup/", views.signup_view, name="signup"),
    path("login/", views.login_view, name="login"),
    path("room/<slug:slug>/", views.room_detail, name="room_detail"),
]