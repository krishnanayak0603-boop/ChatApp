
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.shortcuts import render, get_object_or_404, redirect

from .models import ChatRoom, Message


@login_required(login_url="chat:login")
def room_list(request):
    rooms = ChatRoom.objects.all()
    return render(request, "chat/room_list.html", {"rooms": rooms})


@login_required(login_url="chat:login")
def room_detail(request, slug):
    room = get_object_or_404(ChatRoom, slug=slug)

    # Normal form POST se message aaye toh database mein save karo.
    if request.method == "POST":
        content = request.POST.get("content", "").strip()

        if content:
            Message.objects.create(
                room=room,
                sender=request.user,
                content=content,
            )

        return redirect("chat:room_detail", slug=slug)

    # Database se saare messages load karo.
    messages = (
        Message.objects
        .filter(room=room)
        .select_related("sender")
        .order_by("timestamp", "id")
    )

    return render(
        request,
        "chat/room_detail.html",
        {
            "room": room,
            "messages": messages,
        },
    )


def signup_view(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("chat:room_list")
    else:
        form = UserCreationForm()

    return render(request, "chat/signup.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect("chat:room_list")
    else:
        form = AuthenticationForm(request)

    return render(request, "chat/login.html", {"form": form})


def logout_view(request):
    if request.method == "POST":
        logout(request)
        return redirect("chat:login")

    return redirect("chat:room_list")
